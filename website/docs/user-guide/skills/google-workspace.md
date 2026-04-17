     1|---
     2|sidebar_position: 2
     3|sidebar_label: "Google Workspace"
     4|title: "Google Workspace — Gmail, Calendar, Drive, Sheets & Docs"
     5|description: "Send email, manage calendar events, search Drive, read/write Sheets, and access Docs — all through OAuth2-authenticated Google APIs"
     6|---
     7|
     8|# Google Workspace Skill
     9|
    10|Gmail, Calendar, Drive, Contacts, Sheets, and Docs integration for Hermes. Uses OAuth2 with automatic token refresh. Prefers the [Google Workspace CLI (`gws`)](https://github.com/nicholasgasior/gws) when available for broader coverage, and falls back to Google's Python client libraries otherwise.
    11|
    12|**Skill path:** `skills/productivity/google-workspace/`
    13|
    14|## Setup
    15|
    16|The setup is fully agent-driven — ask Hermes to set up Google Workspace and it walks you through each step. The flow:
    17|
    18|1. **Create a Google Cloud project** and enable the required APIs (Gmail, Calendar, Drive, Sheets, Docs, People)
    19|2. **Create OAuth 2.0 credentials** (Desktop app type) and download the client secret JSON
    20|3. **Authorize** — Hermes generates an auth URL, you approve in the browser, paste back the redirect URL
    21|4. **Done** — token auto-refreshes from that point on
    22|
    23|:::tip Email-only users
    24|If you only need email (no Calendar/Drive/Sheets), use the **himalaya** skill instead — it works with a Gmail App Password and takes 2 minutes. No Google Cloud project needed.
    25|:::
    26|
    27|## Gmail
    28|
    29|### Searching
    30|
    31|```bash
    32|$GAPI gmail search "is:unread" --max 10
    33|$GAPI gmail search "from:boss@company.com newer_than:1d"
    34|$GAPI gmail search "has:attachment filename:pdf newer_than:7d"
    35|```
    36|
    37|Returns JSON with `id`, `from`, `subject`, `date`, `snippet`, and `labels` for each message.
    38|
    39|### Reading
    40|
    41|```bash
    42|$GAPI gmail get MESSAGE_ID
    43|```
    44|
    45|Returns the full message body as text (prefers plain text, falls back to HTML).
    46|
    47|### Sending
    48|
    49|```bash
    50|# Basic send
    51|$GAPI gmail send --to user@example.com --subject "Hello" --body "Message text"
    52|
    53|# HTML email
    54|$GAPI gmail send --to user@example.com --subject "Report" \
    55|  --body "<h1>Q4 Results</h1><p>Details here</p>" --html
    56|
    57|# Custom From header (display name + email)
    58|$GAPI gmail send --to user@example.com --subject "Hello" \
    59|  --from '"Research Agent" <user@example.com>' --body "Message text"
    60|
    61|# With CC
    62|$GAPI gmail send --to user@example.com --cc "team@example.com" \
    63|  --subject "Update" --body "FYI"
    64|```
    65|
    66|### Custom From Header
    67|
    68|The `--from` flag lets you customize the sender display name on outgoing emails. This is useful when multiple agents share the same Gmail account but you want recipients to see different names:
    69|
    70|```bash
    71|# Agent 1
    72|$GAPI gmail send --to client@co.com --subject "Research Summary" \
    73|  --from '"Research Agent" <shared@company.com>' --body "..."
    74|
    75|# Agent 2
    76|$GAPI gmail send --to client@co.com --subject "Code Review" \
    77|  --from '"Code Assistant" <shared@company.com>' --body "..."
    78|```
    79|
    80|**How it works:** The `--from` value is set as the RFC 5322 `From` header on the MIME message. Gmail allows customizing the display name on your own authenticated email address without any additional configuration. Recipients see the custom display name (e.g. "Research Agent") while the email address stays the same.
    81|
    82|**Important:** If you use a *different email address* in `--from` (not the authenticated account), Gmail requires that address to be configured as a [Send As alias](https://support.google.com/mail/answer/22370) in Gmail Settings → Accounts → Send mail as.
    83|
    84|The `--from` flag works on both `send` and `reply`:
    85|
    86|```bash
    87|$GAPI gmail reply MESSAGE_ID \
    88|  --from '"Support Bot" <shared@company.com>' --body "We're on it"
    89|```
    90|
    91|### Replying
    92|
    93|```bash
    94|$GAPI gmail reply MESSAGE_ID --body "Thanks, that works for me."
    95|```
    96|
    97|Automatically threads the reply (sets `In-Reply-To` and `References` headers) and uses the original message's thread ID.
    98|
    99|### Labels
   100|
   101|```bash
   102|# List all labels
   103|$GAPI gmail labels
   104|
   105|# Add/remove labels
   106|$GAPI gmail modify MESSAGE_ID --add-labels LABEL_ID
   107|$GAPI gmail modify MESSAGE_ID --remove-labels UNREAD
   108|```
   109|
   110|## Calendar
   111|
   112|```bash
   113|# List events (defaults to next 7 days)
   114|$GAPI calendar list
   115|$GAPI calendar list --start 2026-03-01T00:00:00Z --end 2026-03-07T23:59:59Z
   116|
   117|# Create event (timezone required)
   118|$GAPI calendar create --summary "Team Standup" \
   119|  --start 2026-03-01T10:00:00-07:00 --end 2026-03-01T10:30:00-07:00
   120|
   121|# With location and attendees
   122|$GAPI calendar create --summary "Lunch" \
   123|  --start 2026-03-01T12:00:00Z --end 2026-03-01T13:00:00Z \
   124|  --location "Cafe" --attendees "alice@co.com,bob@co.com"
   125|
   126|# Delete event
   127|$GAPI calendar delete EVENT_ID
   128|```
   129|
   130|:::warning
   131|Calendar times **must** include a timezone offset (e.g. `-07:00`) or use UTC (`Z`). Bare datetimes like `2026-03-01T10:00:00` are ambiguous and will be treated as UTC.
   132|:::
   133|
   134|## Drive
   135|
   136|```bash
   137|$GAPI drive search "quarterly report" --max 10
   138|$GAPI drive search "mimeType='application/pdf'" --raw-query --max 5
   139|```
   140|
   141|## Sheets
   142|
   143|```bash
   144|# Read a range
   145|$GAPI sheets get SHEET_ID "Sheet1!A1:D10"
   146|
   147|# Write to a range
   148|$GAPI sheets update SHEET_ID "Sheet1!A1:B2" --values '[["Name","Score"],["Alice","95"]]'
   149|
   150|# Append rows
   151|$GAPI sheets append SHEET_ID "Sheet1!A:C" --values '[["new","row","data"]]'
   152|```
   153|
   154|## Docs
   155|
   156|```bash
   157|$GAPI docs get DOC_ID
   158|```
   159|
   160|Returns the document title and full text content.
   161|
   162|## Contacts
   163|
   164|```bash
   165|$GAPI contacts list --max 20
   166|```
   167|
   168|## Output Format
   169|
   170|All commands return JSON. Key fields per service:
   171|
   172|| Command | Fields |
   173||---------|--------|
   174|| `gmail search` | `id`, `threadId`, `from`, `to`, `subject`, `date`, `snippet`, `labels` |
   175|| `gmail get` | `id`, `threadId`, `from`, `to`, `subject`, `date`, `labels`, `body` |
   176|| `gmail send/reply` | `status`, `id`, `threadId` |
   177|| `calendar list` | `id`, `summary`, `start`, `end`, `location`, `description`, `htmlLink` |
   178|| `calendar create` | `status`, `id`, `summary`, `htmlLink` |
   179|| `drive search` | `id`, `name`, `mimeType`, `modifiedTime`, `webViewLink` |
   180|| `contacts list` | `name`, `emails`, `phones` |
   181|| `sheets get` | 2D array of cell values |
   182|
   183|## Troubleshooting
   184|
   185|| Problem | Fix |
   186||---------|-----|
   187|| `NOT_AUTHENTICATED` | Run setup (ask Hermes to set up Google Workspace) |
   188|| `REFRESH_FAILED` | Token revoked — re-run authorization steps |
   189|| `HttpError 403: Insufficient Permission` | Missing scope — revoke and re-authorize with the right services |
   190|| `HttpError 403: Access Not Configured` | API not enabled in Google Cloud Console |
   191|| `ModuleNotFoundError` | Run setup script with `--install-deps` |
   192|
