/**
 * The smallest service that adds what GitHub cannot: an inbox and a counter.
 *
 * Content is NOT stored here. Recipes live in the repository's recipes/
 * folder, which is public, free, versioned and moderatable by pull request.
 * This holds two things GitHub has no way to do:
 *
 *   an inbox    so someone without a GitHub account can still contribute
 *   a counter   so good tones can surface
 *
 * That split is deliberate and it decides the failure mode. If this worker is
 * down, browsing and using recipes still work, because they read GitHub. All
 * that is lost is submission and ranking, and the client keeps both in a
 * local outbox until this comes back. Nothing a person writes depends on this
 * being up.
 *
 * Counting TRANSMITS, not downloads. The app knows when a recipe actually
 * reached hardware, which is a much better signal than a fetch and far harder
 * to inflate by refreshing a page. Ranking uses recent plays rather than a
 * lifetime total, so a good new tone can surface instead of a leaderboard of
 * whatever was posted first.
 *
 * Deploy: wrangler d1 create tonecommand, then wrangler deploy.
 * Schema is in service/schema.sql.
 */

const CORS = {
  // The app runs on the player's own machine, so the origin is theirs.
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json", ...CORS },
  });

/**
 * A recipe is FM9 instructions, not a file, and this is what makes that true
 * rather than nearly true.
 *
 * The filename was never the risk: `name` is `[a-z0-9-]` only, so the path is
 * always recipes/<name>.json with no traversal and nothing outside that
 * folder. What WAS unbounded was the content. The old check validated the
 * envelope and never looked inside a step, so `steps: [1,2,3]` passed, and
 * publish() writes the whole body, so any extra top-level key a sender
 * invented was preserved verbatim into the repository. With auto-publish on,
 * that is "anyone may write arbitrary JSON into a public repo", which is not
 * what anybody agreed to.
 *
 * So: known keys only, and every step has to be a real action.
 */
const RECIPE_KEYS = new Set([
  "recipe_version", "name", "title", "device", "author", "tested_firmware",
  "sources", "assumes", "summary", "ear_checklist", "actions", "steps",
  "submission_id",
]);

// Kept in step with fm9/planner.py ACTION_KINDS by a test in the Python
// suite, which reads this file. Two lists that must agree and cannot import
// each other need something that fails when they drift.
const ACTION_KINDS = new Set([
  "set_param", "set_scene", "set_bypass", "set_channel", "set_tempo",
  "set_type", "add_block", "reorder", "bind_pedal", "unbind_pedal",
  "rename_preset", "rename_scene",
]);

const TEXT_MAX = 2000;

function readRecipe(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return "not an object";
  }
  if (body.recipe_version !== 1) return "unknown recipe_version";
  if (typeof body.name !== "string" || !/^[a-z0-9-]{1,64}$/.test(body.name)) {
    return "name must be lowercase letters, digits and dashes";
  }
  for (const key of Object.keys(body)) {
    if (!RECIPE_KEYS.has(key)) return `unknown field: ${key}`;
  }
  for (const key of ["title", "device", "author", "tested_firmware",
                     "assumes", "summary"]) {
    if (key in body && typeof body[key] !== "string") return `${key} must be text`;
    if (typeof body[key] === "string" && body[key].length > TEXT_MAX) {
      return `${key} is too long`;
    }
  }
  for (const key of ["sources", "ear_checklist"]) {
    if (!(key in body)) continue;
    if (!Array.isArray(body[key])) return `${key} must be a list`;
    if (body[key].length > 50) return `${key} has too many entries`;
    for (const line of body[key]) {
      if (typeof line !== "string" || line.length > TEXT_MAX) {
        return `${key} must be short text`;
      }
    }
  }
  const steps = body.steps || body.actions;
  if (!Array.isArray(steps) || !steps.length) return "no steps";
  if (steps.length > 200) return "too many steps";
  for (const step of steps) {
    if (!step || typeof step !== "object" || Array.isArray(step)) {
      return "every step must be an object";
    }
    if (!ACTION_KINDS.has(step.kind)) {
      // `store` is deliberately absent from ACTION_KINDS. It is the one
      // action that writes to flash, and a recipe from a stranger has no
      // business overwriting one of the owner's presets. The app would still
      // gate it behind the store whitelist and a confirmation, but a shared
      // recipe should never be asking in the first place.
      return step.kind === "store"
        ? "a shared recipe may not store to a preset slot"
        : `unknown step kind: ${String(step.kind).slice(0, 40)}`;
    }
    for (const key of Object.keys(step)) {
      if (!STEP_KEYS.has(key)) return `unknown field in step: ${key}`;
    }
    for (const [key, val] of Object.entries(step)) {
      if (typeof val === "string" && val.length > TEXT_MAX) {
        return `step ${key} is too long`;
      }
    }
  }
  if (JSON.stringify(body).length > 64 * 1024) return "recipe too large";
  return null;
}

const STEP_KEYS = new Set([
  "kind", "block", "instance", "param", "value", "bypassed", "type_name",
  "position", "bank", "reason", "slot", "slot_label", "effect_id",
]);

/**
 * Commit a recipe into the repository's recipes/ folder.
 *
 * Refuses to overwrite. That is not moderation, it is integrity: without it
 * anyone could POST a recipe named after one of the curated tones and
 * silently replace it, and the catalogue would have no way to tell. A name
 * already taken is a 409 to the sender rather than a clobber nobody notices.
 */
async function publish(env, recipe) {
  const repo = env.RECIPE_REPO || "monzta1/ToneCommand";
  const branch = env.RECIPE_BRANCH || "main";
  const path = `recipes/${recipe.name}.json`;
  const api = `https://api.github.com/repos/${repo}/contents/${path}`;
  const headers = {
    "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "tonecommand-share",
    "Content-Type": "application/json",
  };

  const existing = await fetch(`${api}?ref=${branch}`, { headers });
  if (existing.status === 200) {
    return { ok: false, why: `a recipe called ${recipe.name} already exists` };
  }
  if (existing.status !== 404) {
    return { ok: false, why: `github said ${existing.status} on the name check` };
  }

  // Pretty printed, because these are read by people in a repository, and a
  // one line JSON blob in a pull request diff is unreviewable.
  const content = btoa(
    unescape(encodeURIComponent(JSON.stringify(recipe, null, 2) + "\n")));
  const put = await fetch(api, {
    method: "PUT", headers,
    body: JSON.stringify({
      message: `Recipe: ${recipe.name}`,
      content, branch,
    }),
  });
  if (!put.ok) {
    return { ok: false, why: `github said ${put.status} on the write` };
  }
  const out = await put.json().catch(() => ({}));
  return { ok: true, url: out.content && out.content.html_url };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });

    // --- what has actually been played -------------------------------------
    if (url.pathname === "/stats" && request.method === "GET") {
      // Recent plays, not lifetime. A lifetime total ranks by age.
      const { results } = await env.DB.prepare(
        `SELECT name,
                COUNT(*) AS plays,
                SUM(CASE WHEN at > unixepoch() - 2592000 THEN 1 ELSE 0 END) AS recent
         FROM plays GROUP BY name`
      ).all();
      const stats = {};
      for (const r of results) {
        stats[r.name] = { plays: r.plays, recent: r.recent };
      }
      return json({ stats });
    }

    // --- a recipe actually reached somebody's hardware ----------------------
    if (url.pathname === "/used" && request.method === "POST") {
      const body = await request.json().catch(() => null);
      const name = body && body.name;
      if (typeof name !== "string" || !/^[a-z0-9-]{1,64}$/.test(name)) {
        return json({ error: "bad name" }, 400);
      }
      // The client sends its own id so a retry after a failed response does
      // not count the same play twice. Nothing is lost by retrying, and
      // nothing is double counted either.
      const id = (body.id || crypto.randomUUID()).slice(0, 64);
      await env.DB.prepare(
        `INSERT OR IGNORE INTO plays (id, name, at) VALUES (?, ?, unixepoch())`
      ).bind(id, name).run();
      return json({ ok: true });
    }

    // --- somebody wants to contribute one ----------------------------------
    if (url.pathname === "/submit" && request.method === "POST") {
      const body = await request.json().catch(() => null);
      const why = readRecipe(body);
      if (why) return json({ error: why }, 400);

      const id = (body.submission_id || crypto.randomUUID()).slice(0, 64);
      // Recorded first, whatever happens next. The row is the audit trail:
      // with auto-publish on it is the only record of who sent what and when,
      // and it is what makes the decision reversible later.
      await env.DB.prepare(
        `INSERT OR IGNORE INTO submissions (id, name, body, at, state)
         VALUES (?, ?, ?, unixepoch(), 'queued')`
      ).bind(id, body.name, JSON.stringify(body)).run();

      // AUTO_PUBLISH off (the default) is the original behaviour: queued, and
      // nothing reaches the catalogue until a human moves it. On, a
      // submission is committed straight into recipes/ and is live for
      // everyone immediately.
      //
      // Worth being plain about what that means, because the setting reads
      // milder than it is: this endpoint is unauthenticated, so with it on,
      // anyone who can reach this URL can write a file into a public
      // repository under the owner's account. That is a deliberate choice
      // while there are no users, not an oversight, and it is one flag to
      // undo.
      if (env.AUTO_PUBLISH !== "true") {
        return json({ ok: true, state: "queued" });
      }
      if (!env.GITHUB_TOKEN) {
        return json({ ok: true, state: "queued",
                      note: "auto-publish is on but no GITHUB_TOKEN is set" });
      }
      const published = await publish(env, body);
      await env.DB.prepare(`UPDATE submissions SET state = ? WHERE id = ?`)
        .bind(published.ok ? "published" : "queued", id).run();
      return published.ok
        ? json({ ok: true, state: "published", url: published.url })
        // A publish that failed is not a lost recipe: the row is already in,
        // the client's outbox entry only clears on a 2xx, and the file can be
        // moved by hand exactly as before.
        : json({ ok: true, state: "queued", note: published.why });
    }

    return json({ error: "not found" }, 404);
  },
};
