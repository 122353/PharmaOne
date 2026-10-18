import type {ScanFields} from './scan';

export type BrowserOcrResult = {
  text: string;
  fields: Partial<ScanFields>;
};

function labelled(text: string, pattern: RegExp, maxLength: number): string {
  const match = text.match(pattern);
  return match?.[1]?.trim().slice(0, maxLength) || '';
}

/** Extract only explicitly labelled values; leave ambiguous identifiers for the pharmacist. */
export function parsePackagingText(text: string): Partial<ScanFields> {
  const clean = text.replace(/\r/g, '').slice(0, 8000);
  const fields: Partial<ScanFields> = {};
  const medicine = labelled(clean, /(?:^|\n)\s*(?:medicine|product|drug name)\s*[:#-]\s*([^\n]+)/i, 255);
  const manufacturer = labelled(clean, /(?:^|\n)\s*(?:manufacturer|manufactured by|mfr)\s*[:#-]\s*([^\n]+)/i, 255);
  const batch = labelled(clean, /\b(?:batch(?:\s*(?:no\.?|number))?|lot(?:\s*no\.?)?|b\.?\s*no\.?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{1,39})\b/i, 120);
  const strength = labelled(clean, /(?:^|\n)\s*strength\s*[:#-]\s*([^\n]+)/i, 100);
  const manufacturingDate = labelled(clean, /(?:^|\n)\s*(?:manufacturing date|mfg\.?\s*date|mfg)\s*[:#-]\s*([0-9A-Za-z/-]{4,30})/i, 30);
  const expiryDate = labelled(clean, /(?:^|\n)\s*(?:expiry date|expiry|exp\.?\s*date|exp)\s*[:#-]\s*([0-9A-Za-z/-]{4,30})/i, 30);
  if (medicine) fields.medicine_name = medicine;
  if (manufacturer) fields.manufacturer = manufacturer;
  if (batch) fields.batch_number = batch;
  if (strength) fields.strength = strength;
  if (manufacturingDate) fields.manufacturing_date = manufacturingDate;
  if (expiryDate) fields.expiry_date = expiryDate;
  return fields;
}

async function preprocess(file: File): Promise<HTMLCanvasElement> {
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size === 0 || file.size > 5 * 1024 * 1024) {
    throw new Error('Choose a PNG or JPEG image up to 5 MB.');
  }
  const bitmap = await createImageBitmap(file);
  try {
    if (!bitmap.width || !bitmap.height || bitmap.width * bitmap.height > 20_000_000) {
      throw new Error('Image dimensions are too large.');
    }
    const scale = Math.min(2, Math.max(1, 1400 / Math.max(bitmap.width, bitmap.height)));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext('2d', {willReadFrequently: true});
    if (!context) throw new Error('This browser cannot process the image.');
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    for (let offset = 0; offset < image.data.length; offset += 4) {
      const gray = Math.round(image.data[offset] * .299 + image.data[offset + 1] * .587 + image.data[offset + 2] * .114);
      const contrast = Math.max(0, Math.min(255, (gray - 128) * 1.45 + 128));
      image.data[offset] = contrast;
      image.data[offset + 1] = contrast;
      image.data[offset + 2] = contrast;
    }
    context.putImageData(image, 0, 0);
    return canvas;
  } finally {
    bitmap.close();
  }
}

/** OCR and image preprocessing stay in the user's browser; no package image is uploaded. */
export async function recognizePackaging(file: File, onProgress?: (message: string) => void): Promise<BrowserOcrResult> {
  const image = await preprocess(file);
  const {createWorker} = await import('tesseract.js');
  const worker = await createWorker('eng', 1, {
    logger: status => {
      if (status.status === 'recognizing text' && typeof status.progress === 'number') {
        onProgress?.(`Reading image… ${Math.round(status.progress * 100)}%`);
      }
    },
  });
  try {
    const result = await worker.recognize(image);
    const text = result.data.text.slice(0, 8000).trim();
    return {text, fields: parsePackagingText(text)};
  } finally {
    await worker.terminate();
  }
}
