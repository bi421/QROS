from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/manual", tags=["manual_setup"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="mn">
<head>
    <meta charset="UTF-8">
    <title>ResearchOS Manual Setup</title>
</head>
<body>
    <h1>ResearchOS Manual Setup</h1>
    <div id="status_container">
        <span id="status_1">Loading...</span>
    </div>
    <script>
        function updateStatus(id, message) {
            const statusSpan = document.getElementById('status_' + id);
            if (statusSpan) {
                statusSpan.textContent = message;
                statusSpan.style.color = "green";
            }
        }
        setTimeout(() => updateStatus(1, "Ready"), 1000);
    </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def manual_setup_page() -> str:
    return DASHBOARD_HTML
