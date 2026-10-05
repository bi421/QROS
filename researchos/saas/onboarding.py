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
const WORKSPACE_NAME_KEY = "qros:onboarding:workspace-name";

const statusElement = document.getElementById("status");
const resultElement = document.getElementById("result");
const workspaceNameElement = document.getElementById("workspace-name");

function setStatus(message) {
  statusElement.textContent = message;
}

function rememberWorkspaceName() {
  const workspaceName = workspaceNameElement.value.trim();
  if (workspaceName) {
    localStorage.setItem(WORKSPACE_NAME_KEY, workspaceName);
  }
  return workspaceName;
}

function restoreWorkspaceName() {
  const workspaceName = localStorage.getItem(WORKSPACE_NAME_KEY);
  if (workspaceName) {
    workspaceNameElement.value = workspaceName;
  }
  return workspaceName || "";
}

function consumeSupabaseAccessToken() {
  const fragment = new URLSearchParams(location.hash.replace(/^#/, ""));
  const token = fragment.get("access_token");
  if (!token) {
    return false;
  }
  accessToken = token;
  history.replaceState(null, document.title, location.pathname + location.search);
  return true;
}

function clearRememberedWorkspaceName() {
  localStorage.removeItem(WORKSPACE_NAME_KEY);
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
  const normalizedName = workspaceName.trim();
  if (!normalizedName) {
    throw new Error("Workspace name is required");
  }
  const workspace = await qrosApi("/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({ name: normalizedName }),
  });
  const me = await qrosApi("/v1/me");
  clearRememberedWorkspaceName();
  resultElement.textContent = JSON.stringify({ workspace, me }, null, 2);
  setStatus("Onboarding complete.");
}

async function handleSignup(event) {
  event.preventDefault();
  try {
    setStatus("Creating account...");
    const workspaceName = rememberWorkspaceName();
    if (!workspaceName) {
      throw new Error("Workspace name is required");
    }
    await loadConfig();
    const data = await supabaseAuth("/signup", {
      email: document.getElementById("signup-email").value,
      password: document.getElementById("signup-password").value,
      options: { emailRedirectTo: location.origin + "/onboarding" },
    });
    if (!data.access_token) {
      setStatus("Account created. Check your email and confirm it. QROS will resume onboarding automatically.");
      return;
    }
    accessToken = data.access_token;
    await finishOnboarding(workspaceName);
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
      workspaceNameElement.value.trim() || "My QROS Workspace";
    await finishOnboarding(workspaceName);
  } catch (error) {
    if (error.message === "workspace already provisioned") {
      try {
        const me = await qrosApi("/v1/me");
        clearRememberedWorkspaceName();
        resultElement.textContent = JSON.stringify({ me }, null, 2);
        setStatus("Signed in. Your workspace is already provisioned.");
        return;
      } catch (meError) {
        setStatus(meError.message);
        return;
      }
    }
    setStatus(error.message);
  }
}

async function resumeConfirmedSignup() {
  if (!consumeSupabaseAccessToken()) {
    return;
  }
  try {
    await loadConfig();
    const workspaceName = restoreWorkspaceName();
    if (!workspaceName) {
      setStatus("Email confirmed. Enter your workspace name to finish onboarding.");
      return;
    }
    setStatus("Email confirmed. Finishing onboarding...");
    await finishOnboarding(workspaceName);
  } catch (error) {
    setStatus(error.message);
  }
}

restoreWorkspaceName();
document.getElementById("signup").addEventListener("submit", handleSignup);
document.getElementById("signin").addEventListener("submit", handleSignin);
resumeConfirmedSignup();
"""
