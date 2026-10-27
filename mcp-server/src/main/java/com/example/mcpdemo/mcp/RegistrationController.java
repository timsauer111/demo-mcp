package com.example.mcpdemo.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestClient;

/** Provider-neutral DCR: HTTPS callbacks and exact local HTTP callbacks, always with PKCE. */
@RestController
class RegistrationController {
    static final String PATH = "/auth/realms/mcp-demo/clients-registrations/openid-connect";
    private final RestClient keycloak;
    private final ObjectMapper mapper;

    RegistrationController(@Value("${demo.registration-base:http://localhost:8080/realms/mcp-demo/clients-registrations/openid-connect}") String base,
                           ObjectMapper mapper) {
        this.keycloak = TokenExchange.http().baseUrl(base).build();
        this.mapper = mapper;
    }

    @PostMapping(PATH)
    ResponseEntity<?> register(@RequestBody JsonNode metadata) {
        return forward(HttpMethod.POST, "", metadata, null);
    }

    @RequestMapping(value = PATH + "/{id}", method = {RequestMethod.GET, RequestMethod.PUT, RequestMethod.DELETE})
    ResponseEntity<?> manage(@PathVariable String id, @RequestBody(required = false) JsonNode metadata,
                             @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
                             jakarta.servlet.http.HttpServletRequest request) {
        if (!id.matches("[a-zA-Z0-9_-]+")) return error(400, "invalid_client_metadata");
        return forward(HttpMethod.valueOf(request.getMethod()), "/" + id, metadata, authorization);
    }

    private ResponseEntity<?> forward(HttpMethod method, String path, JsonNode metadata, String authorization) {
        if ((method == HttpMethod.POST || method == HttpMethod.PUT) && !validRedirects(metadata))
            return error(400, "invalid_redirect_uri");
        try {
            var request = keycloak.method(method).uri(path).contentType(MediaType.APPLICATION_JSON);
            if (authorization != null) request.header(HttpHeaders.AUTHORIZATION, authorization);
            if (metadata != null) request.body(mapper.writeValueAsBytes(metadata));
            return request.exchange((req, response) -> ResponseEntity.status(response.getStatusCode())
                .contentType(MediaType.APPLICATION_JSON).header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(response.getBody().readAllBytes()));
        } catch (Exception error) {
            return error(502, "registration_unavailable");
        }
    }

    static boolean validRedirects(JsonNode metadata) {
        JsonNode redirects = metadata == null ? null : metadata.get("redirect_uris");
        if (redirects == null || !redirects.isArray() || redirects.isEmpty() || redirects.size() > 16) return false;
        for (JsonNode redirect : redirects) {
            if (!redirect.isTextual()) return false;
            try {
                String value = redirect.textValue();
                URI uri = URI.create(value);
                String host = uri.getHost();
                boolean loopback = "localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host) || "[::1]".equals(host);
                if (host == null || uri.getRawUserInfo() != null || uri.getRawFragment() != null
                    || value.contains("*") || value.toLowerCase(java.util.Locale.ROOT).contains("%2a")
                    || !("https".equals(uri.getScheme()) || ("http".equals(uri.getScheme()) && loopback))
                    || uri.getPort() > 65535) return false;
            } catch (IllegalArgumentException error) { return false; }
        }
        return true;
    }

    private static ResponseEntity<?> error(int status, String code) {
        return ResponseEntity.status(status).header(HttpHeaders.CACHE_CONTROL, "no-store").body(Map.of("error", code));
    }
}
