import {expect, test} from '@playwright/test';
import {parsePackagingText} from '../lib/browser-ocr';

test('labelled medicine packaging values are extracted without inventing fields', () => {
  const fields = parsePackagingText('Medicine: Synthetic Test Medicine\nManufacturer: Example Labs\nBatch: SYN123\nStrength: 10 mg\nMfg Date: 01/2026\nExpiry: 12/2027');
  expect(fields).toEqual({
    medicine_name: 'Synthetic Test Medicine', manufacturer: 'Example Labs', batch_number: 'SYN123',
    strength: '10 mg', manufacturing_date: '01/2026', expiry_date: '12/2027',
  });
  expect(parsePackagingText('Synthetic Test Medicine\nExample Labs\n12/2027').batch_number).toBeUndefined();
  expect(parsePackagingText('Medicine: Similar Drug\nBatch: WRONG').batch_number).toBe('WRONG');
});
