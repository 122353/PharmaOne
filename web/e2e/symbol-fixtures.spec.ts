import {expect, test} from '@playwright/test';
import {BarcodeFormat, BinaryBitmap, DecodeHintType, HybridBinarizer, MultiFormatReader, QRCodeReader, QRCodeWriter, RGBLuminanceSource} from '@zxing/library';
import {decodeLabel} from '../lib/scan';

function bitmap(width:number, height:number, dark:(x:number,y:number)=>boolean){
  const pixels=new Int32Array(width*height);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++)pixels[y*width+x]=dark(x,y)?0xff000000:0xffffffff;
  return new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels,width,height)));
}

test('synthetic medicine QR fixture decodes exact identifiers',()=>{
  const label=JSON.stringify({medicine_name:'Synthetic Test Medicine',batch_number:'SYN123'});
  const matrix=new QRCodeWriter().encode(label,BarcodeFormat.QR_CODE,300,300,new Map());
  const reader=new MultiFormatReader();
  reader.setHints(new Map([[DecodeHintType.POSSIBLE_FORMATS,[BarcodeFormat.QR_CODE]]]));
  const decoded=reader.decodeWithState(bitmap(matrix.getWidth(),matrix.getHeight(),(x,y)=>matrix.get(x,y)));
  expect(decoded.getBarcodeFormat()).toBe(BarcodeFormat.QR_CODE);
  expect(decoded.getText()).toBe(label);
  expect(decodeLabel(decoded.getText()).batch_number).toBe('SYN123');
});

test('synthetic product-only EAN-13 fixture has no batch identifier',()=>{
  const digits='5901234123457';
  const left=['0001101','0011001','0010011','0111101','0100011','0110001','0101111','0111011','0110111','0001011'];
  const odd=['0100111','0110011','0011011','0100001','0011101','0111001','0000101','0010001','0001001','0010111'];
  const right=['1110010','1100110','1101100','1000010','1011100','1001110','1010000','1000100','1001000','1110100'];
  const parity='LGGLLG';
  const bits='101'+[...digits.slice(1,7)].map((digit,i)=>(parity[i]==='L'?left:odd)[Number(digit)]).join('')+'01010'+
    [...digits.slice(7)].map(digit=>right[Number(digit)]).join('')+'101';
  const scale=4,quiet=12;
  const width=(bits.length+quiet*2)*scale;
  const reader=new MultiFormatReader();
  reader.setHints(new Map([[DecodeHintType.POSSIBLE_FORMATS,[BarcodeFormat.EAN_13]]]));
  const decoded=reader.decodeWithState(bitmap(width,100,(x,y)=>{
    const bit=Math.floor(x/scale)-quiet;
    return y>=10&&y<90&&bit>=0&&bit<bits.length&&bits[bit]==='1';
  }));
  expect(decoded.getText()).toBe(digits);
  expect(decodeLabel(decoded.getText()).batch_number).toBeUndefined();
});

test('blank symbol fixture is rejected',()=>{
  expect(()=>new QRCodeReader().decode(bitmap(200,200,()=>false))).toThrow();
});
