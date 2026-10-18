export type ScanFields={medicine_name:string;manufacturer:string;batch_number:string;strength:string;manufacturing_date:string;expiry_date:string};

const fieldNames:(keyof ScanFields)[]=['medicine_name','manufacturer','batch_number','strength','manufacturing_date','expiry_date'];

export function decodeLabel(value:string):Partial<ScanFields>{
  try {
    const parsed=value.trim().startsWith('{')?JSON.parse(value):Object.fromEntries(new URL(value).searchParams);
    const output:Partial<ScanFields>={};
    for(const key of fieldNames){
      const source=parsed[key]||parsed[key==='medicine_name'?'medicine':key==='batch_number'?'batch':key];
      if(typeof source==='string')output[key]=source.slice(0,255);
    }
    return output;
  }catch{return {}}
}
