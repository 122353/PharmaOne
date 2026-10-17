import { createClient } from '@supabase/supabase-js';

const url = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';
export const configured = Boolean(url && key && !url.includes('your-project'));
export const supabase = configured ? createClient(url, key) : null;
