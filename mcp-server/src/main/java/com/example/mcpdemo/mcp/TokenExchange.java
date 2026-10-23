package com.example.mcpdemo.mcp;

import com.example.mcpdemo.security.JwtSecurity;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

@Component
class TokenExchange {
    private final RestClient client;
    private final String secret;
    private final JwtDecoder apiDecoder;

    TokenExchange(@Value("${demo.issuer}") String issuer, @Value("${demo.client-secret}") String secret) {
        this.secret = secret;
        this.apiDecoder = JwtSecurity.decoder(issuer, "tickets-api");
        this.client = http().baseUrl(issuer + "/protocol/openid-connect/token").build();
    }

    static RestClient.Builder http() {
        var http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER).build();
        var factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofSeconds(8));
        return RestClient.builder().requestFactory(factory);
    }

    record Subject(String token, String userId) {
        @Override public String toString() { return "Subject[redacted]"; }
    }
    record TokenResponse(@JsonProperty("access_token") String accessToken) {
        @Override public String toString() { return "TokenResponse[redacted]"; }
    }

    String exchange(Subject subject) {
        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "urn:ietf:params:oauth:grant-type:token-exchange");
        form.add("subject_token", subject.token());
        form.add("subject_token_type", "urn:ietf:params:oauth:token-type:access_token");
        form.add("requested_token_type", "urn:ietf:params:oauth:token-type:access_token");
        form.add("audience", "tickets-api");
        // No optional scopes. Keycloak role-scope mappings impose the read-only ceiling.
        var response = client.post().headers(h -> h.setBasicAuth("mcp-server", secret))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED).body(form).retrieve().body(TokenResponse.class);
        if (response == null || response.accessToken() == null) throw new IllegalStateException("Exchange rejected");
        var jwt = apiDecoder.decode(response.accessToken());
        var roles = JwtSecurity.roles("tickets-api", List.of("tickets.read", "tickets.write")).convert(jwt);
        if (!subject.userId().equals(jwt.getSubject()) || !jwt.getAudience().equals(List.of("tickets-api"))
            || roles == null || roles.size() != 1 || !roles.iterator().next().getAuthority().equals("tickets.read")) {
            throw new IllegalStateException("Exchange policy rejected");
        }
        return response.accessToken();
    }
}
