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
    <section id="research-workspace" hidden>
      <h2>Research workspace</h2>
      <p>Upload an XAUUSD M1 CSV, then run the governed research workflow. A completed run is not proof of profitability.</p>
      <form id="dataset-upload">
        <label for="dataset-name">Dataset name</label>
        <input id="dataset-name" name="name" required maxlength="256" value="XAUUSD M1 dataset">
        <label for="dataset-file">CSV file</label>
        <input id="dataset-file" name="file" type="file" accept=".csv,text/csv" required>
        <button type="submit">Upload dataset</button>
      </form>
      <p id="dataset-state" role="status" aria-live="polite"></p>
      <label for="dataset-version">Immutable dataset version</label>
      <select id="dataset-version" required></select>
      <button id="run-research" type="button">Run Research</button>
      <button id="refresh-runs" type="button">Refresh runs</button>
      <h3>Research runs</h3>
      <div id="research-runs" aria-live="polite"></div>
      <h3>Report and evidence</h3>
      <pre id="research-detail"></pre>
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
  showResearchWorkspace();
}

function showResearchWorkspace() {
  document.getElementById("research-workspace").hidden = false;
  loadDatasetsAndRuns().catch((error) => setResearchStatus(error.message));
}

function setResearchStatus(message) {
  document.getElementById("dataset-state").textContent = message;
}

function showResearchDetail(value) {
  document.getElementById("research-detail").textContent = JSON.stringify(value, null, 2);
}

async function uploadDataset(event) {
  event.preventDefault();
  const file = document.getElementById("dataset-file").files[0];
  const name = document.getElementById("dataset-name").value.trim();
  if (!file || !name) {
    setResearchStatus("Choose a CSV file and enter a dataset name.");
    return;
  }
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  setResearchStatus("Uploading and hashing dataset...");
  const response = await fetch("/v1/datasets", {
    method: "POST",
    headers: accessToken ? { Authorization: "Bearer " + accessToken } : {},
    body: form,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || data.detail || "Dataset upload failed");
  }
  const version = data.version;
  if (!version || !version.id) {
    throw new Error("Upload response did not include an immutable dataset version.");
  }
  const select = document.getElementById("dataset-version");
  const option = document.createElement("option");
  option.value = version.id;
  option.textContent = name + " — v" + version.version_no + " — SHA-256 " + version.content_sha256;
  select.appendChild(option);
  select.value = version.id;
  setResearchStatus("Upload complete. Dataset version and content hash received.");
  showResearchDetail({ dataset_id: data.id, version });
}

async function loadDatasetsAndRuns() {
  const datasets = await qrosApi("/v1/datasets?page=1&page_size=100");
  const select = document.getElementById("dataset-version");
  for (const dataset of (datasets.data || [])) {
    if (dataset.version && dataset.version.id && !Array.from(select.options).some((option) => option.value === dataset.version.id)) {
      const option = document.createElement("option");
      option.value = dataset.version.id;
      option.textContent = dataset.name + " — v" + dataset.version.version_no + " — SHA-256 " + dataset.version.content_sha256;
      select.appendChild(option);
    }
  }
  const runs = await qrosApi("/v1/research-runs?page=1&page_size=50");
  const container = document.getElementById("research-runs");
  container.replaceChildren();
  for (const run of (runs.data || [])) {
    const item = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = run.status + " — " + run.id;
    const view = document.createElement("button");
    view.type = "button";
    view.textContent = "View result";
    view.addEventListener("click", () => inspectResearchRun(run.id).catch((error) => setResearchStatus(error.message)));
    item.append(label, view);
    container.appendChild(item);
  }
  if (!container.childElementCount) {
    container.textContent = "No research runs yet.";
  }
}

async function startResearch() {
  const datasetVersionId = document.getElementById("dataset-version").value;
  if (!datasetVersionId) {
    throw new Error("Upload a dataset or select an existing dataset version first.");
  }
  const idempotencyKey = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + "-" + Math.random().toString(16).slice(2));
  setResearchStatus("Submitting governed research run...");
  const run = await qrosApi("/v1/research-runs", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      dataset_version_id: datasetVersionId,
      workflow_id: "xauusd_m1_frozen_research_v1",
    }),
  });
  showResearchDetail(run);
  setResearchStatus("Research run queued. Refresh to see server-reported status.");
  await loadDatasetsAndRuns();
}

async function inspectResearchRun(jobId) {
  setResearchStatus("Loading run status and report...");
  const status = await qrosApi("/v1/research-runs/" + encodeURIComponent(jobId));
  let report;
  try {
    report = await qrosApi("/v1/research-runs/" + encodeURIComponent(jobId) + "/report");
  } catch (error) {
    report = { report_unavailable: error.message };
  }
  let evidence;
  try {
    evidence = await qrosApi("/v1/research-runs/" + encodeURIComponent(jobId) + "/evidence?page=1&page_size=50");
  } catch (error) {
    evidence = { evidence_unavailable: error.message };
  }
  showResearchDetail({ status, report, evidence });
  setResearchStatus("Displayed server-reported run state, report, and evidence. No profitability claim is inferred.");
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
        showResearchWorkspace();
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
document.getElementById("dataset-upload").addEventListener("submit", (event) => uploadDataset(event).catch((error) => setResearchStatus(error.message)));
document.getElementById("run-research").addEventListener("click", () => startResearch().catch((error) => setResearchStatus(error.message)));
document.getElementById("refresh-runs").addEventListener("click", () => loadDatasetsAndRuns().catch((error) => setResearchStatus(error.message)));
resumeConfirmedSignup();
"""
