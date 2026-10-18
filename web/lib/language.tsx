'use client';
import {createContext,useContext,useEffect,useState} from 'react';

export type Language='en'|'hi';
const LanguageContext=createContext<{language:Language;setLanguage:(value:Language)=>void}>({language:'en',setLanguage:()=>{}});
export function LanguageProvider({children}:{children:React.ReactNode}){
  const [language,setLanguage]=useState<Language>('en');
  useEffect(()=>{const saved=localStorage.getItem('pharmaone-language');if(saved==='hi')setLanguage('hi')},[]);
  useEffect(()=>{document.documentElement.lang=language},[language]);
  function update(value:Language){setLanguage(value);localStorage.setItem('pharmaone-language',value)}
  return <LanguageContext.Provider value={{language,setLanguage:update}}>{children}</LanguageContext.Provider>;
}
export function useLanguage(){return useContext(LanguageContext)}
export const navText={
  en:['Dashboard','Inventory','Scan Medicine','Regulatory Alerts','Investigations','Supplier Exposure','ContextOS','Settings','Pharmacy workspace','Sign out'],
  hi:['डैशबोर्ड','इन्वेंटरी','दवा स्कैन करें','नियामक अलर्ट','जाँच','आपूर्तिकर्ता संबंध','ContextOS','सेटिंग्स','फार्मेसी कार्यक्षेत्र','साइन आउट'],
};
