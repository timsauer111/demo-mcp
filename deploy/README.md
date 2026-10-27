# Betrieb der gehosteten MCP-Demo

Die Demo läuft als eigener Compose-Stack `mcp-demo-hosted` unter `/opt/mcp-demo` auf dem VPS. Öffentlicher Einstieg ist `https://srv1424016.hstgr.cloud/mcp`. Caddy stellt das TLS-Zertifikat automatisch aus und erneuert es. Es ist kein zusätzlicher Cloud-Dienst und kein DNS-Eingriff erforderlich.

## Deployment

Auf dem Entwicklungsrechner werden JDK 21, Python 3.11+ und SSH benötigt. Der VPS benötigt Docker mit Compose, seine öffentliche IPv4-Adresse und einen bereits darauf zeigenden DNS-Namen. Port 80 und 443 müssen auf der öffentlichen Schnittstelle frei und erreichbar sein. Der feste Callback `127.0.0.1:8766` liegt auf dem Rechner mit Codex, nicht auf dem VPS.

```sh
./demo hosted deploy
./demo hosted status
./demo hosted verify
```

`deploy` führt zuerst den Maven-Build inklusive Java-Tests lokal aus. Es überträgt die beiden JARs, Compose, Proxy und Realm-Generator per SSH. Ein eigener Marker schützt vor dem Überschreiben eines fremden Zielverzeichnisses. Es werden weder andere Stacks gestoppt noch Images oder Volumes anderer Projekte gelöscht.

Nach dem Start gleicht `scripts/hosted_registration.py` die begrenzte App-Registrierung über die nur lokal erreichbare Keycloak-Administration ab. Der Abgleich funktioniert auch mit einem bereits importierten Realm und wird bei jedem Deployment wiederholt. Ein privater Konfigurations-Snapshot liegt unter `.hosted/registration-before.json`.

Beim ersten Aufruf generiert der VPS eigene Passwörter und ein Exchange-Secret. Lokale Demo-Secrets aus `.local` werden nicht übertragen. Das Verzeichnis `.hosted` hat Modus 0700; Secrets und Env-Datei 0600. Nur die Realm-Importdatei hat 0640, damit Keycloak als UID 1000/GID 0 den eingebundenen Import lesen kann. Der übergeordnete Ordner bleibt für andere Benutzer gesperrt. Nach erfolgreichem Deployment werden die Zugangsdaten über SSH im lokal ignorierten `.hosted` abgelegt. Werte werden nicht ausgegeben.

`status` prüft den Stack sowie MCP-Health und OAuth-Discovery über öffentliches HTTPS. `verify` führt die Rechte-Matrix über die öffentliche HTTPS-API und den öffentlichen MCP aus. Währenddessen werden ausschließlich synthetische Testtickets angelegt und anschließend die drei Seed-Tickets wiederhergestellt.

Andere Zielsysteme sind mit `--host SSH_ALIAS --hostname DNS_NAME --public-ip IPV4` möglich. Dazu zuvor die öffentliche URL in `integrations/codex-hosted.toml` ändern. Hostname und IP sind pro Installation fest: Der Setup-Helfer verweigert eine stillschweigende Änderung eines bestehenden Issuers. Bestehende Secrets werden niemals automatisch rotiert.

## Öffentliche und interne Zugriffe

| Bereich | Erreichbarkeit |
|---|---|
| `/mcp` | Öffentlich über HTTPS; OAuth erforderlich |
| `/api/*` | Öffentliche REST-API; Tickets benötigen ein API-Token mit passenden Rollen |
| `/health`, `/.well-known/oauth-protected-resource[/mcp]` | Öffentlich; keine Zugangsdaten oder Tickets |
| `/auth/realms/mcp-demo/*`, `/auth/resources/*` | Öffentlicher Demo-Login, Discovery, Schlüssel und Token-Endpunkt |
| Keycloak-Admin, Realm `master`, alle anderen Pfade | Kein öffentlicher Proxy-Zugriff |
| Keycloak intern | VPS-Loopback `127.0.0.1:18080` |
| Ticket-Backend intern | VPS-Loopback `127.0.0.1:18081` |
| PostgreSQL | Nur im separaten Docker-Netz |

Die öffentlichen Ports sind ausschließlich an `187.77.76.126` gebunden. Der vorhandene Tailscale-HTTPS-Listener bleibt dadurch verfügbar. Interne Aufrufe zum öffentlichen Issuer laufen im Stack über einen DNS-Alias des Caddy-Containers mit normaler TLS-Prüfung. Die Backend-Adresse ist fest `http://ticket-api:8081`; Toolargumente können sie nicht ersetzen.

Caddy prüft die Übereinstimmung von TLS-SNI und HTTP-Host. Der MCP prüft zusätzlich den konfigurierten Host und Origin. Keycloak läuft mit `start`, festem HTTPS-Hostname, Proxy-Headern, S256-PKCE und Brute-Force-Schutz. Anonyme DCR ist anbieterunabhängig und auf höchstens 32 Realm-Clients begrenzt. Der MCP-Registrierungscontroller prüft neue und geänderte Rückleitungsadressen: HTTPS oder HTTP ausschließlich für die literalen Loopback-Hosts `localhost`, `127.0.0.1`, `[::1]`; keine Wildcards, Fragmente oder Benutzerinformationen. Caddy führt ausschließlich den OpenID-Registrierungspfad zu diesem Controller; andere Registrierungsprovider sind öffentlich gesperrt. Keycloak erzwingt S256-PKCE, Consent und die MCP-Scope-Grenze. Registrierungstokens werden von Keycloak selbst geprüft und gehören nicht zur MCP-Token-Audience. Neue App-Clients erhalten `mcp.access` als Default-Scope mit festem Subject-/Audience-Mapping; `openid` und `offline_access` sind zulässig, Backend-Scopes und selbst definierte Mapper nicht. Ein Keycloak-Clientprofil erzwingt S256 und deaktiviert Password-/Implicit-Grant bei anonymer Registrierung und Updates per Registrierungstoken. Vorregistrierte CLI-Clients werden dabei nicht umkonfiguriert. Die Proxy-Header werden am Ingress gesetzt. Die Demo verwendet keinen Password Grant für Benutzerlogins.

Es sind keine Access-Logs aktiviert. Für Runtime-Fehler entfernt Caddy Request-URI und Header aus der Logausgabe, damit auch bei einem Upstream-Ausfall keine OAuth-Querys im Fehlerlog stehen. Docker-Logs sind pro Container auf zweimal 5 MB begrenzt.

## Neustart, Updates und Stilllegung

Auf dem VPS:

```sh
cd /opt/mcp-demo
docker compose -f compose.hosted.yaml --env-file .hosted/docker.env ps
docker compose -f compose.hosted.yaml --env-file .hosted/docker.env restart
```

Die App-Registrierung ist eine explizite, idempotente Migration. Für spätere andere Realm-Änderungen gilt weiterhin die folgende Importgrenze.

Code-Updates erfolgen mit `./demo hosted deploy` vom Entwicklungsrechner. Ein erneutes Deployment erhält Datenbank-Volume, Realm und Secrets. **Realm-Imports werden von Keycloak nur beim ersten Anlegen übernommen.** Eine spätere Rollen-/Clientänderung benötigt eine gezielte administrative Migration; ein erneuter Import allein reicht nicht. Dateien und Container werden bei Updates in demselben Stack ersetzt; die Demo bietet dabei keine unterbrechungsfreie Auslieferung.

Zum Stilllegen:

```sh
cd /opt/mcp-demo
docker compose -f compose.hosted.yaml --env-file .hosted/docker.env down
```

Volumes und Konfiguration bleiben dabei erhalten. Zum erneuten Start denselben Befehl mit `up -d` verwenden. Für einen Umzug müssen `.hosted` und das Keycloak-Datenbank-Volume gemeinsam gesichert werden. Keine Zugangsdaten ins Repository übernehmen.

Die Anwendungen und Caddy starten nach einem VPS-/Docker-Neustart durch `restart: unless-stopped` erneut. Es gibt keine automatische Überwachung oder Alarmierung.

## Kapazität und Grenzen

Der vorhandene VPS hatte beim Start rund 2,2 GB freien Speicher. Deshalb laufen die beiden Java-JARs mit dem bereits für Keycloak benötigten Java-21-Image; es ist kein weiteres Runtime-/Buildimage nötig. PostgreSQL verwendet ein bereits vorhandenes, per Digest fixiertes 17.11-Image, aber eine **eigene Datenbank und ein eigenes Volume**.

Container haben Speicherlimits und begrenzte Logs. Nach der Einrichtung bleibt trotzdem wenig Plattenreserve. Vor einem größeren Image-Update freien Speicher prüfen; die Demo bereinigt keine fremden Daten. Das ist eine kleine Präsentationsinstallation ohne Verfügbarkeitszusage, generisches Benutzer-Onboarding oder produktive Ticketpersistenz. Die Ticketdaten werden bei Backend-Neustart zurückgesetzt.

## Codex-Zugang

```sh
./demo hosted credentials  # nur Betreiber: Zugangsdaten sicher per SSH abrufen
./demo hosted install      # öffentliche Verbindung in persönliche Codex-Konfiguration ergänzen
./demo hosted login        # Browser-Login; Codex speichert OAuth im Schlüsselbund
./demo hosted run          # tatsächliche Toolereignisse eines separaten Agenten prüfen
./demo hosted logout       # lokale Codex-Zugangsdaten entfernen
```

`logout` entfernt gespeicherte Zugangsdaten, widerruft aber keine Keycloak-Offline-Sitzung. Bei Bedarf diese administrativ beim synthetischen Benutzer beenden. Für die persönliche Nutzung in einer neuen Codex-Session ist nur der eingerichtete MCP und der Login nötig; kein SSH-Tunnel.
