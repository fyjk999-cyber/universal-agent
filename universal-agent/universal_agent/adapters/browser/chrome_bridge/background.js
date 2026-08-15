// GENERATED template (logic stable; allowlist lives in bridge-policy.mjs).
import { airlineForHost, officialAirlineUrl } from './bridge-policy.mjs';

const localAppOrigin = 'http://127.0.0.1:8632';

function isApprovedSender(sender) {{
  try {{
    return new URL(sender.url).origin === localAppOrigin;
  }} catch {{
    return false;
  }}
}}

function errorResponse(error) {{
  return {{ ok: false, error }};
}}

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {{
  if (!isApprovedSender(sender)) {{
    sendResponse(errorResponse('UNAUTHORIZED_ORIGIN'));
    return;
  }}

  if (!message || typeof message.type !== 'string') {{
    sendResponse(errorResponse('INVALID_MESSAGE'));
    return;
  }}

  if (message.type === 'ping') {{
    sendResponse({{ ok: true, version: chrome.runtime.getManifest().version }});
    return;
  }}

  if (message.type === 'launchOfficial') {{
    const url = officialAirlineUrl(message.url);
    if (!url) {{
      sendResponse(errorResponse('UNAPPROVED_AIRLINE_URL'));
      return;
    }}
    chrome.tabs.create({{ url: url.href, active: true }})
      .then((tab) => sendResponse({{ ok: true, tab: {{ id: tab.id, host: url.hostname, airline: airlineForHost(url.hostname) }} }}))
      .catch(() => sendResponse(errorResponse('TAB_CREATE_FAILED')));
    return true;
  }}

  if (message.type === 'getOpenAirlineTabs') {{
    chrome.tabs.query({{}})
      .then((tabs) => tabs.flatMap((tab) => {{
        const url = officialAirlineUrl(tab.url || '');
        return url ? [{{ id: tab.id, host: url.hostname, airline: airlineForHost(url.hostname) }}] : [];
      }}))
      .then((tabs) => sendResponse({{ ok: true, tabs }}))
      .catch(() => sendResponse(errorResponse('TAB_QUERY_FAILED')));
    return true;
  }}

  sendResponse(errorResponse('UNSUPPORTED_ACTION'));
}});
