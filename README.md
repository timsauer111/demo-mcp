# Ticket-Demo: MCP und REST-API im Vergleich

Diese Demo zeigt, wie sich der Zugriff eines KI-Assistenten auf eine bestehende API begrenzen lässt: Die Ticket-API unterstützt Lesen und Schreiben. Der vorgeschaltete MCP-Server stellt dagegen nur zwei Lesewerkzeuge bereit – auch für einen Benutzer, der direkt an der API schreiben darf.

Die Demo ist bereits gehostet und verwendet synthetische Tickets. Für die MCP-Nutzung müssen Sie dieses Repository nicht installieren.

| Zugriff | Lesen | Erstellen, Ändern, Löschen |
|---|---|---|
| MCP-Server in der KI-App | Ja, über zwei MCP-Tools | Nein, keine Schreibtools vorhanden |
| REST-API mit entsprechend berechtigtem API-Token | Ja | Ja |

## MCP-Server in der KI-Oberfläche einbinden

**Server-URL:** `https://srv1424016.hstgr.cloud/mcp`

**Transport:** Streamable HTTP

**Anmeldung:** OAuth 2 mit Authorization Code und PKCE

### Codex-App

1. In Codex **Plugins → Benutzerdefinierter MCP-Server hinzufügen** öffnen.
2. Einen Namen, zum Beispiel `Ticket-Demo`, und die Server-URL eintragen. Als Authentifizierung **OAuth** auswählen und die Verbindung hinzufügen.
3. Im geöffneten Browser mit dem separat bereitgestellten Demo-Benutzernamen und Passwort anmelden und die angeforderten Berechtigungen bestätigen.
4. Die Verbindung für die Codex-Sitzung aktivieren und zum Beispiel fragen:

   > Nutze die Ticket-Demo, zeige mir die offenen Tickets und lies Ticket 1 vollständig.

Die Zugangsdaten werden für die Anmeldung bei Keycloak verwendet; sie gehören nicht in die Repository-Dateien. Je nach Codex-Oberfläche kann die Bezeichnung der Menüpunkte abweichen. Die Verbindung verwendet OAuth und keine manuelle Eingabe eines API-Tokens.

### Claude Web und Claude Desktop

1. **Anpassungen / Customize → Konnektoren / Connectors → Konnektor hinzufügen → Benutzerdefinierten Konnektor hinzufügen** öffnen.
2. Einen Namen und `https://srv1424016.hstgr.cloud/mcp` eintragen und auf **Weiter** klicken.
3. OAuth verwenden und, falls die Auswahl angeboten wird, **Register automatically / Automatisch registrieren** auswählen.
4. **Jetzt anmelden / Sign in now** wählen, den Connector hinzufügen und im Browser mit den separat bereitgestellten Demo-Zugangsdaten anmelden.
5. Den Connector im Claude-Chat aktivieren und beispielsweise „Liste die offenen Tickets und lies Ticket 1“ eingeben.

Die Verbindung wird über das Claude-Konto verwaltet und kann in Claude Web und Desktop verwendet werden. Bei Team- und Enterprise-Konten wird der Connector zunächst von einem entsprechend berechtigten Administrator hinzugefügt. [Claude-Anleitung](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)

### Gemini und weitere KI-Oberflächen

In Gemini Web unter **Settings → Connected Apps → Custom apps** die MCP-URL `https://srv1424016.hstgr.cloud/mcp` hinzufügen und die Browser-Anmeldung mit den Demo-Zugangsdaten durchlaufen. Die Verfügbarkeit eigener Apps hängt von Googles Konto- und Regionsfreigabe ab; siehe [Gemini-Anleitung](https://support.google.com/gemini/answer/17209137).

In anderen KI-Oberflächen mit Unterstützung für eigene Remote-MCP-Server dieselbe URL als **Streamable-HTTP-Server mit OAuth** hinzufügen. Der Server bietet OAuth-Discovery und Dynamic Client Registration; eine eigene Client-ID oder ein Clientsecret müssen dafür nicht vorab beschafft werden. Falls die Oberfläche Scopes abfragt: `mcp.access`, optional `offline_access` für erneuerbare Sitzungen.

Der Server ist nicht an einen Anbieter gebunden. Er unterstützt Authorization Code mit **S256-PKCE** und exakte HTTPS-Rückleitungen der jeweiligen KI-Oberfläche. Die verfügbaren Werkzeuge und die Beschränkung auf Lesen sind bei allen MCP-Clients gleich.

## MCP-Werkzeuge

| Werkzeug | Funktion | Parameter |
|---|---|---|
| `list_tickets` | Tickets auflisten und optional nach Status filtern | `status`: `OPEN`, `IN_PROGRESS` oder `CLOSED` (optional); `offset` (optional, ab 0); `limit` (optional, 1–100) |
| `get_ticket` | Ein einzelnes Ticket lesen | `id`: positive ganzzahlige Ticket-ID |

Der Server bietet weder Schreibwerkzeuge noch einen allgemeinen HTTP-Proxy an. Eine Aufforderung wie „Ändere Ticket 1“ kann daher nicht über diese MCP-Verbindung ausgeführt werden.

## Direkter Zugriff auf die REST-API

Die API prüft OAuth-Bearer-Tokens und die enthaltenen API-Rollen. Der Demo-Benutzer besitzt bei direkter Anmeldung über den API-Client Lese- und Schreibrechte. Die API stellt folgende Operationen bereit:

| Methode und Pfad | Funktion | Erforderliche Rolle |
|---|---|---|
| `GET /tickets` | Tickets auflisten; optional `status`, `offset`, `limit` | `tickets.read` |
| `GET /tickets/{id}` | Ticket lesen | `tickets.read` |
| `POST /tickets` | Ticket erstellen | `tickets.write` |
| `PATCH /tickets/{id}` | Ticket ändern | `tickets.write` |
| `DELETE /tickets/{id}` | Ticket löschen | `tickets.write` |
| `POST /demo/reset` | Synthetische Beispieldaten zurücksetzen | `tickets.write` |

**API-Basisadresse:** `https://srv1424016.hstgr.cloud/api`

Die API ist über HTTPS erreichbar. Die vollständige Schnittstellenbeschreibung steht als [OpenAPI-Datei](https://srv1424016.hstgr.cloud/api/openapi.yaml) bereit; der [Quelltext](ticket-api/src/main/resources/static/openapi.yaml) liegt ebenfalls im Repository.

### Authentifizierung

Ein OAuth-fähiger API-Client verwendet **Authorization Code mit PKCE (S256)** und diese Einstellungen für die gehostete Instanz:

| Einstellung | Wert |
|---|---|
| Authorization URL | `https://srv1424016.hstgr.cloud/auth/realms/mcp-demo/protocol/openid-connect/auth` |
| Token URL | `https://srv1424016.hstgr.cloud/auth/realms/mcp-demo/protocol/openid-connect/token` |
| Client-ID | `api-demo-client` |
| Client-Typ | Public Client, kein Clientsecret |
| Redirect URI (Postman, Browser-Anmeldung) | `https://oauth.pstmn.io/v1/browser-callback` |
| Scopes | `tickets.read tickets.write` |

**Beispiel mit Postman:** Unter **Authorization → OAuth 2.0 → Get New Access Token** den Grant Type **Authorization Code (With PKCE)** und die Werte aus der Tabelle eintragen. Als Code Challenge Method **SHA-256 / S256** und als Client Authentication **Send client credentials in body** auswählen; das Clientsecret bleibt leer. **Authorize using browser** aktivieren, **Get New Access Token** starten, mit dem Demo-Benutzernamen und dem separat bereitgestellten Passwort anmelden und anschließend **Use Token** auswählen. Der Authorization-Header wird von Postman gesetzt.

Für Postmans alternative Callback-Variante ist auch `https://oauth.pstmn.io/v1/callback` registriert. Eigene lokale API-Clients können `http://127.0.0.1:8765/callback` verwenden und müssen den Callback dort selbst entgegennehmen.

Nach der Browser-Anmeldung tauscht der API-Client den Authorization Code mit dem PKCE-Verifier gegen ein Access-Token und sendet dieses als `Authorization: Bearer <API_ACCESS_TOKEN>` an die API. Benutzername und Passwort werden im Loginformular eingegeben; sie werden nicht als API-Parameter übertragen. Ein MCP-Token ist für den MCP-Server bestimmt und ersetzt das API-Token nicht.

Beispiele für direkte HTTPS-Aufrufe mit dem vom OAuth-Client bezogenen `API_ACCESS_TOKEN`:

```sh
API_BASE="https://srv1424016.hstgr.cloud/api"

curl "$API_BASE/tickets" -H "Authorization: Bearer $API_ACCESS_TOKEN"

curl -X POST "$API_BASE/tickets" \
  -H "Authorization: Bearer $API_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Beispielticket","description":"Synthetische Anfrage","status":"OPEN"}'

curl -X PATCH "$API_BASE/tickets/1" \
  -H "Authorization: Bearer $API_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"CLOSED"}'

curl -X DELETE "$API_BASE/tickets/1" -H "Authorization: Bearer $API_ACCESS_TOKEN"
```

Fehlt ein gültiges Token, antwortet die API mit `401`; fehlen die benötigten Rollen, mit `403`. Die Ticketdaten liegen im Arbeitsspeicher und werden beim Neustart des Backends auf die Beispieldaten zurückgesetzt.

## Wie die Begrenzung funktioniert

Der MCP-Server prüft zunächst das für ihn ausgestellte OAuth-Token. Für den Zugriff auf die Ticket-API tauscht er es bei Keycloak gegen ein separates Backend-Token aus. Dieses erhält nur die Rolle `tickets.read`, unabhängig von den weitergehenden direkten API-Rechten des Benutzers. Die API prüft ihre Rollen selbst und verweigert Schreibaufrufe mit diesem Token.

Der [technische Nachweis](docs/PUBLIC-DEMO-VERIFICATION.md) beschreibt einen Test mit einem tatsächlich ausgetauschten Token: Lesen war erfolgreich; POST, PATCH, DELETE und Reset wurden jeweils mit `403` abgewiesen und die Daten blieben unverändert. Das ist eine serverseitig durchgesetzte Grenze, keine bloße Anweisung an das Modell.

Der Quellcode liegt in [mcp-server](mcp-server/), [ticket-api](ticket-api/) und [security-common](security-common/). Keycloak übernimmt die Authentifizierung und den Token-Austausch.
