import { supabase } from './supabase';

const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export async function api<T>(path:string, init:RequestInit={}):Promise<T> {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session) throw new Error('Sign in to continue');
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${session.access_token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type','application/json');
  const response = await fetch(`${base}${path}`, {...init, headers, cache:'no-store'});
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export type Alert = {fingerprint:string;product_name:string;manufacturer:string;batch_number:string;quality_issue:string;reporting_period:string;reporting_source:string;source_url:string;retrieved_at:string;classification:string};
export type Inventory = {id:string;medicine_name:string;manufacturer:string;batch_number:string;strength:string;expiry_date:string;quantity:number;quality_state:string};
export type Match = {id:string;status:string;explanation:Record<string,{inventory:string;source:string;aligned?:boolean;exact?:boolean}>;inventory:Inventory;alert:Alert};
export type Source = {state:string;last_checked:string|null;record_count:number;source_url:string;error:string};
export type Dashboard = {pharmacy:string;inventory_count:number;potential_count:number;verification_count:number;open_investigations:number;review_queue:Match[];recent_alerts:Alert[];clarifications:string[];source:Source};
