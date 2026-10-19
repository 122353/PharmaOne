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

export type Alert = {fingerprint:string;product_name:string;manufacturer:string;batch_number:string;quality_issue:string;reporting_period:string;reporting_source:string;source_url:string;retrieved_at:string;classification:string;pharma_classify?:{model:string;version:string;category:string;confidence:number;advisory_only:boolean}};
export type Inventory = {id:string;medicine_name:string;manufacturer:string;batch_number:string;strength:string;expiry_date:string;quantity:number;quality_state:string};
export type StrengthValue = {value_mg:string;basis:string};
export type MatchExplanation = {
  product:{inventory:string;source:string;aligned?:boolean;inventory_ingredients?:string[];source_ingredients?:string[];inventory_form?:string[];source_form?:string[];form_aligned?:boolean|null;inventory_release?:string[];source_release?:string[];release_aligned?:boolean|null};
  batch:{inventory:string;source:string;exact?:boolean};
  manufacturer:{inventory:string;source:string;aligned?:boolean};
  strength?:{inventory:StrengthValue[];inventory_name:StrengthValue[];inventory_field:StrengthValue[];source:StrengthValue[];aligned:boolean|null;inventory_conflict:boolean;duplicate_sources:boolean};
  pharma_match?:{model:string;version?:string;product_similarity?:number;advisory_only:boolean;available?:boolean};
  semantic_match?:{model:string;semantic_similarity?:number;advisory_only:boolean;candidate_retrieved?:boolean;available?:boolean};
};
export type Match = {id:string;status:string;explanation:MatchExplanation;inventory:Inventory;alert:Alert};
export type Source = {state:string;last_checked:string|null;record_count:number;source_url:string;error:string;historical_snapshot_imported:boolean;snapshot_imported_at:string|null;snapshot_reporting_period:string|null;retrieval_metadata:Record<string,unknown>};
export type Dashboard = {
  pharmacy: string;
  inventory_count: number;
  potential_count: number;
  verification_count: number;
  open_investigations: number;
  review_queue: Match[];
  recent_alerts: Alert[];
  clarifications: string[];
  source: Source;
  unread_notifications?: number;
};

export type MonitoringNotification = {
  id: string;
  event_id: string;
  inventory_id: string;
  alert_id: string;
  status: string;
  title: string;
  message: string;
  is_read: boolean;
  is_active: boolean;
  medicine_name: string;
  batch_number: string;
  quality_issue: string;
  reporting_period: string;
  source_url: string;
  created_at: string;
};
