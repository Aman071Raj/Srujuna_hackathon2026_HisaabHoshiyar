// ==============================================================================
// Shared Supabase Client File
// Reads Supabase URL and anon key from environment configuration / window / backend
// ==============================================================================

(function(global) {
  const SUPABASE_CONFIG = {
    url: (global.ENV && global.ENV.SUPABASE_URL) || 'https://mskltxhhszqvqhbgaxbm.supabase.co',
    anonKey: (global.ENV && (global.ENV.SUPABASE_ANON_KEY || global.ENV.SUPABASE_KEY)) || 'sb_publishable_C6HOmjdGbROzrAQom5Jn5A_9mCNWqfc'
  };

  let _client = null;

  function initClient() {
    if (_client) return _client;
    const lib = global.supabase;
    if (!lib || !lib.createClient) {
      console.warn('Supabase JS library not yet loaded. Client will initialize once library is ready.');
      return null;
    }
    _client = lib.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true
      }
    });
    global.supabaseClient = _client;
    return _client;
  }

  global.SUPABASE_CONFIG = SUPABASE_CONFIG;
  global.getSupabaseClient = initClient;
  
  // Try initializing immediately if library is already present
  if (global.supabase) {
    initClient();
  }
})(typeof window !== 'undefined' ? window : this);
