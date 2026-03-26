Param(
  [string]$AppBaseUrl = $env:APP_BASE_URL,
  [string]$CollaboraBaseUrl = $env:COLLABORA_BASE_URL,
  [string]$OfficeDocId = $env:WOPI_OFFICE_DOC_ID,
  [string]$SessionCookie = $env:APP_SESSION_COOKIE
)

python scripts/verify_collabora_wopi_smoke.py `
  --app-base "$AppBaseUrl" `
  --collabora-base "$CollaboraBaseUrl" `
  --office-doc-id "$OfficeDocId" `
  --session-cookie "$SessionCookie"
