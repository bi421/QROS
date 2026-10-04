"""Minimal customer self-service onboarding boundary for QROS."""

ONBOARDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; connect-src 'self' https://*.supabase.co; style-src 'self'">
  <title>QROS — Start Research</title>
</head>
<body>
  <main>
    <h1>QROS</h1>
    <p>Create your research workspace.</p>
    <section>
      <h2>Create account</h2>
      <form id="signup">
        <input id="signup-email" type="email" autocomplete="email" required placeholder="Email">
        <input id="signup-password" type="password" autocomplete="new-password" minlength="8" required placeholder="Password">
        <input id="workspace-name" required maxlength="256" placeholder="Workspace name">
        <button type="submit">Create account</button>
      </form>
    </section>
    <section>
      <h2>Already have an account?</h2>
      <form id="signin">
        <input id="signin-email" type="email" autocomplete="email" required placeholder="Email">
        <input id="signin-password" type="password" autocomplete="current-password" required placeholder="Password">
        <button type="submit">Sign in</button>
      </form>
    </section>
    <p id="status" role="status" aria-live="polite"></p>
    <pre id="result"></pre>
  </main>
  <script src="/onboarding/app.js" defer></script>
</body>
</html>
"""

ONBOARDING_JS = """let config = null;
let accessToken = null;

const statusElement = document.getElementById("status");
const resultElement = document.getElementById("result");

function setStatus(message) {
  statusElement.textContent = message;
}

async function loadConfig() {
  const response = await fetch("/onboarding/config", {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("QROS onboarding is not configured");
  }
  config = await response.json();
}

async function supabaseAuth(path, body) {
  const response = await fetch(
    config.supabase_url + "/auth/v1" + path,
    {
      method: "POST",
      headers: {
        apikey: config.supabase_publishable_key,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );
  const data = await response.json();
  if (!response.ok) {
    throw new Error(
      data.msg || data.message || data.error_description || "Authentication failed"
    );
  }
  return data;
}

async function qrosApi(path, options = {}) {
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    options.headers || {}
  );
  if (accessToken) {
    headers.Authorization = "Bearer " + accessToken;
  }
  const response = await fetch(path, Object.assign({}, options, { headers }));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || data.detail || "Request failed");
  }
  return data;
}

async function finishOnboarding(workspaceName) {
  const workspace = await qrosApi("/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({ name: workspaceName }),
  });
  const me = await qrosApi("/v1/me");
  resultElement.textContent = JSON.stringify({ workspace, me }, null, 2);
  setStatus("Onboarding complete.");
}

async function handleSignup(event) {
  event.preventDefault();
  try {
    setStatus("Creating account...");
    await loadConfig();
    const data = await supabaseAuth("/signup", {
      email: document.getElementById("signup-email").value,
      password: document.getElementById("signup-password").value,
      options: { emailRedirectTo: location.origin + "/onboarding" },
    });
    if (!data.access_token) {
      setStatus("Account created. Check your email, confirm it, then sign in below.");
      return;
    }
    accessToken = data.access_token;
    await finishOnboarding(document.getElementById("workspace-name").value.trim());
  } catch (error) {
    setStatus(error.message);
  }
}

async function handleSignin(event) {
  event.preventDefault();
  try {
    setStatus("Signing in...");
    await loadConfig();
    const data = await supabaseAuth("/token?grant_type=password", {
      email: document.getElementById("signin-email").value,
      password: document.getElementById("signin-password").value,
    });
    accessToken = data.access_token;
    const workspaceName =
      document.getElementById("workspace-name").value.trim() || "My QROS Workspace";
    try {
      await finishOnboarding(workspaceName);
    } catch (error) {
      if (error.message === "workspace already provisioned") {
        const me = await qrosApi("/v1/me");
        resultElement.textContent = JSON.stringify({ me }, null, 2);
        setStatus("Signed in. Your workspace is already provisioned.");
        return;
      }
      throw error;
    }
  } catch (error) {
    setStatus(error.message);
  }
}

document.getElementById("signup").addEventListener("submit", handleSignup);
document.getElementById("signin").addEventListener("submit", handleSignin);
"""
