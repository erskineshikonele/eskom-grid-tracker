// supabase/functions/esp-proxy/index.ts
// Proxies requests to EskomSePush API to bypass CORS restrictions
// on GitHub Pages. Keeps the ESP token server-side.

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";

const ESP_TOKEN = Deno.env.get("ESP_TOKEN")!;
const ESP_BASE  = "https://developer.sepush.co.za/business/2.0";

const CORS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, apikey",
};

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }

  const url    = new URL(req.url);
  const action = url.searchParams.get("action"); // status | areas_search | area
  const text   = url.searchParams.get("text");
  const id     = url.searchParams.get("id");

  let espUrl = "";

  if (action === "status") {
    espUrl = `${ESP_BASE}/status`;
  } else if (action === "areas_search" && text) {
    espUrl = `${ESP_BASE}/areas_search?text=${encodeURIComponent(text)}`;
  } else if (action === "area" && id) {
    espUrl = `${ESP_BASE}/area?id=${encodeURIComponent(id)}`;
  } else {
    return new Response(
      JSON.stringify({ error: "Invalid action or missing parameters" }),
      { status: 400, headers: { ...CORS, "Content-Type": "application/json" } }
    );
  }

  try {
    const espRes = await fetch(espUrl, {
      headers: { "token": ESP_TOKEN },
    });

    const data = await espRes.json();

    return new Response(JSON.stringify(data), {
      status: espRes.status,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: { ...CORS, "Content-Type": "application/json" } }
    );
  }
});
