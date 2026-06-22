// supabase/functions/send-grid-alert/index.ts
// Triggered manually or via cron after each weekly scrape.
// Checks if EAF dropped 2%+ week-on-week OR load shedding returned,
// then emails all active subscribers via Resend.

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY")!;
const SUPABASE_URL   = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY   = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const FROM_EMAIL     = "Eskom Grid Tracker <onboarding@resend.dev>";
const DASHBOARD_URL  = "https://erskineshikonele.github.io/eskom-grid-tracker";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

// ─── Alert conditions ─────────────────────────────────
interface AlertResult {
  shouldAlert: boolean;
  type: "load_shedding_returned" | "eaf_drop" | "none";
  subject: string;
  message: string;
}

async function checkAlertConditions(): Promise<AlertResult> {
  // Fetch last 2 rows ordered by report_date desc
  const { data, error } = await supabase
    .from("eskom_grid_metrics")
    .select("report_date, eaf_ytd_pct, consec_days_no_ls")
    .order("report_date", { ascending: false })
    .limit(2);

  if (error || !data || data.length < 2) {
    console.log("Not enough data to compare:", error);
    return { shouldAlert: false, type: "none", subject: "", message: "" };
  }

  const latest = data[0];
  const prev   = data[1];

  // Check if streak was broken (load shedding returned)
  if (
    latest.consec_days_no_ls !== null &&
    prev.consec_days_no_ls !== null &&
    latest.consec_days_no_ls < prev.consec_days_no_ls
  ) {
    return {
      shouldAlert: true,
      type: "load_shedding_returned",
      subject: "⚠️ Load shedding has returned — Eskom Grid Alert",
      message: `
        <p>The consecutive-days streak has been broken.</p>
        <p>South Africa had gone <strong>${prev.consec_days_no_ls} days</strong> without load shedding.</p>
        <p>The latest Eskom report (${latest.report_date}) indicates the streak has ended.</p>
        <p>Monitor the situation at the dashboard.</p>
      `,
    };
  }

  // Check if EAF dropped 2%+ week-on-week
  if (
    latest.eaf_ytd_pct !== null &&
    prev.eaf_ytd_pct !== null &&
    prev.eaf_ytd_pct - latest.eaf_ytd_pct >= 2.0
  ) {
    const drop = (prev.eaf_ytd_pct - latest.eaf_ytd_pct).toFixed(2);
    return {
      shouldAlert: true,
      type: "eaf_drop",
      subject: `📉 EAF dropped ${drop}% this week — Eskom Grid Early Warning`,
      message: `
        <p>The Energy Availability Factor (EAF) has dropped significantly this week.</p>
        <ul>
          <li>Previous week: <strong>${prev.eaf_ytd_pct}%</strong></li>
          <li>This week: <strong>${latest.eaf_ytd_pct}%</strong></li>
          <li>Drop: <strong>${drop}%</strong></li>
        </ul>
        <p>This may be an early warning sign. Monitor the dashboard closely.</p>
      `,
    };
  }

  return { shouldAlert: false, type: "none", subject: "", message: "" };
}

// ─── Check if already alerted this week ──────────────
async function alreadyAlerted(reportDate: string, alertType: string): Promise<boolean> {
  const { data } = await supabase
    .from("alert_log")
    .select("id")
    .eq("report_date", reportDate)
    .eq("alert_type", alertType)
    .limit(1);
  return !!(data && data.length > 0);
}

// ─── Fetch subscribers ────────────────────────────────
async function getSubscribers(): Promise<string[]> {
  const { data, error } = await supabase
    .from("alert_subscribers")
    .select("email")
    .eq("active", true);
  if (error || !data) return [];
  return data.map((r: { email: string }) => r.email);
}

// ─── Send email via Resend ────────────────────────────
async function sendAlert(
  to: string[],
  subject: string,
  bodyHtml: string,
  latestDate: string
): Promise<void> {
  const html = `
    <!DOCTYPE html>
    <html>
    <body style="font-family:Inter,sans-serif;background:#0d1117;color:#f1f5f9;padding:32px;max-width:600px;margin:0 auto;">
      <div style="background:#131c27;border:1px solid #1e3048;border-radius:10px;padding:24px;">
        <h2 style="color:#e8a020;font-size:1.1rem;margin:0 0 16px;">⚡ Eskom Grid Recovery Tracker</h2>
        <p style="color:#94a3b8;font-size:0.8rem;margin:0 0 20px;">Weekly alert — ${latestDate}</p>
        <div style="color:#f1f5f9;font-size:0.95rem;line-height:1.7;">
          ${bodyHtml}
        </div>
        <div style="margin-top:24px;padding-top:16px;border-top:1px solid #1e3048;">
          <a href="${DASHBOARD_URL}"
             style="display:inline-block;background:#e8a020;color:#0d1117;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:0.85rem;">
            View Dashboard
          </a>
        </div>
        <p style="color:#6b7280;font-size:0.72rem;margin-top:20px;">
          You're receiving this because you subscribed to Eskom grid alerts.
          Data sourced from official Eskom weekly press releases.
        </p>
      </div>
    </body>
    </html>
  `;

  // Send to each subscriber individually (Resend free tier)
  for (const email of to) {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM_EMAIL,
        to: [email],
        subject,
        html,
      }),
    });
    const result = await res.json();
    console.log(`Sent to ${email}:`, result);
  }
}

// ─── Log alert ────────────────────────────────────────
async function logAlert(alertType: string, reportDate: string, recipientCount: number) {
  await supabase.from("alert_log").insert({
    alert_type: alertType,
    report_date: reportDate,
    recipient_count: recipientCount,
  });
}

// ─── Main handler ─────────────────────────────────────
serve(async (req) => {
  try {
    console.log("Checking alert conditions...");
    const alert = await checkAlertConditions();

    if (!alert.shouldAlert) {
      return new Response(
        JSON.stringify({ status: "ok", message: "No alert conditions met." }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    // Get latest report date
    const { data: latest } = await supabase
      .from("eskom_grid_metrics")
      .select("report_date")
      .order("report_date", { ascending: false })
      .limit(1);
    const reportDate = latest?.[0]?.report_date ?? new Date().toISOString().slice(0, 10);

    // Dedup — don't send the same alert twice
    if (await alreadyAlerted(reportDate, alert.type)) {
      return new Response(
        JSON.stringify({ status: "ok", message: "Already alerted for this week." }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    const subscribers = await getSubscribers();
    if (subscribers.length === 0) {
      return new Response(
        JSON.stringify({ status: "ok", message: "No active subscribers." }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    await sendAlert(subscribers, alert.subject, alert.message, reportDate);
    await logAlert(alert.type, reportDate, subscribers.length);

    return new Response(
      JSON.stringify({
        status: "sent",
        alert_type: alert.type,
        recipients: subscribers.length,
        report_date: reportDate,
      }),
      { headers: { "Content-Type": "application/json" } }
    );

  } catch (err) {
    console.error("Edge function error:", err);
    return new Response(
      JSON.stringify({ status: "error", message: String(err) }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
});
