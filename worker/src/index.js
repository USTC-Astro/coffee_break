const DRINKS = [
  "其他（填备注中）", "生椰拿铁", "瑞之抹茶", "鲜萃轻轻茉莉",
  "柚C美式", "精萃澳瑞白", "柠C美式", "标准美式",
  "苹果C美式", "茉莉花香拿铁", "加浓美式",
  "生椰杨枝甘露", "橙C美式", "小黄油拿铁",
  "羽衣轻体果蔬茶", "小黄油美式", "轻椰茉莉拿铁", "冰吸生椰拿铁",
  "埃塞金烘美式", "苦瓜轻体美式", "陨石拿铁"
];

const WEEK_RE = /^(current|\d{4}-\d{2}-\d{2}-[A-Za-z]{3})$/;
const JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"};

function allowedOrigins(env) {
  return (env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function corsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowed = allowedOrigins(env);
  const allowOrigin = allowed.includes("*") || allowed.includes(origin) ? origin : allowed[0] || "";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin"
  };
}

function json(data, status = 200, request, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {...JSON_HEADERS, ...corsHeaders(request, env)}
  });
}

function badRequest(message, request, env) {
  return json({ok: false, error: message}, 400, request, env);
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

async function ipKey(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "unknown";
  const secret = env.IP_HASH_SECRET || "coffee-break";
  const data = new TextEncoder().encode(`${secret}:${ip}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function checkRateLimit(request, env) {
  const key = await ipKey(request, env);
  const bucket = String(Math.floor(Date.now() / 60000));
  const maxPerMinute = Number(env.MAX_VOTES_PER_MINUTE || 12);
  const row = await env.DB.prepare(
    "SELECT count FROM rate_limits WHERE key = ? AND bucket = ?"
  ).bind(key, bucket).first();
  const nextCount = (row?.count || 0) + 1;
  await env.DB.prepare(
    `INSERT INTO rate_limits (key, bucket, count, updated_at)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(key, bucket) DO UPDATE SET count = ?, updated_at = CURRENT_TIMESTAMP`
  ).bind(key, bucket, nextCount, nextCount).run();
  return nextCount <= maxPerMinute;
}

async function listVotes(week, request, env) {
  const result = await env.DB.prepare(
    "SELECT device_id, drink, name, updated_at FROM coffee_votes WHERE week = ? ORDER BY updated_at ASC"
  ).bind(week).all();
  const votes = {};
  for (const row of result.results || []) {
    votes[row.device_id] = {
      drink: row.drink,
      name: row.name,
      time: (row.updated_at || "").slice(0, 16).replace("T", " ")
    };
  }
  return json({votes}, 200, request, env);
}

async function saveVote(week, request, env) {
  const body = await readJson(request);
  const voteCode = (env.COFFEE_VOTE_CODE || "").trim();
  if (voteCode && body.code !== voteCode) {
    return json({ok: false, error: "Invalid vote code"}, 403, request, env);
  }
  if (!(await checkRateLimit(request, env))) {
    return json({ok: false, error: "Too many requests"}, 429, request, env);
  }

  const drink = String(body.drink || "").trim();
  const name = String(body.name || "anomaly").trim().slice(0, 40) || "anomaly";
  const deviceId = String(body.device_id || name).trim().slice(0, 120);
  if (!deviceId) return badRequest("Missing device_id", request, env);
  if (!DRINKS.includes(drink)) return badRequest("Invalid drink", request, env);

  await env.DB.prepare(
    `INSERT INTO coffee_votes (week, device_id, drink, name, created_at, updated_at)
     VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
     ON CONFLICT(week, device_id) DO UPDATE SET
       drink = excluded.drink,
       name = excluded.name,
       updated_at = CURRENT_TIMESTAMP`
  ).bind(week, deviceId, drink, name).run();
  return listVotes(week, request, env);
}

async function cancelVote(week, request, env) {
  const body = await readJson(request);
  const deviceId = String(body.device_id || "").trim().slice(0, 120);
  if (!deviceId) return badRequest("Missing device_id", request, env);
  await env.DB.prepare(
    "DELETE FROM coffee_votes WHERE week = ? AND device_id = ?"
  ).bind(week, deviceId).run();
  return listVotes(week, request, env);
}

async function refreshVotes(request, env) {
  const token = new URL(request.url).searchParams.get("token") || "";
  if (!env.ADMIN_TOKEN || token !== env.ADMIN_TOKEN) {
    return json({ok: false, error: "Forbidden"}, 403, request, env);
  }
  const archiveId = new Date().toISOString().replace(/[:.]/g, "-");
  await env.DB.prepare(
    `INSERT INTO coffee_vote_archives (archive_id, week, device_id, drink, name, voted_at)
     SELECT ?, week, device_id, drink, name, updated_at FROM coffee_votes WHERE week = 'current'`
  ).bind(archiveId).run();
  await env.DB.prepare("DELETE FROM coffee_votes WHERE week = 'current'").run();
  return json({ok: true, archive_id: archiveId}, 200, request, env);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, {headers: corsHeaders(request, env)});
    }

    const url = new URL(request.url);
    const parts = url.pathname.replace(/^\/+|\/+$/g, "").split("/");

    if (parts[0] === "health") {
      return json({ok: true}, 200, request, env);
    }

    if (parts[0] === "coffee_votes" && WEEK_RE.test(parts[1] || "")) {
      const week = parts[1];
      if (request.method === "GET" && parts.length === 2) {
        return listVotes(week, request, env);
      }
      if (request.method === "POST" && parts.length === 2) {
        return saveVote(week, request, env);
      }
      if (request.method === "POST" && parts[2] === "cancel") {
        return cancelVote(week, request, env);
      }
    }

    if (request.method === "POST" && parts[0] === "admin" && parts[1] === "refresh_votes") {
      return refreshVotes(request, env);
    }

    return json({ok: false, error: "Not found"}, 404, request, env);
  }
};
