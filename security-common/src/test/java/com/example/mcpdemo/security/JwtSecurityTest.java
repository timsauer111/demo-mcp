package com.example.mcpdemo.security;

import static org.assertj.core.api.Assertions.*;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class JwtSecurityTest {
    private Jwt.Builder valid() {
        return Jwt.withTokenValue("unit-fixture").header("alg", "RS256").issuer("http://issuer.test")
            .audience(List.of("tickets-api")).subject("user-1").claim("typ", "Bearer")
            .issuedAt(Instant.now().minusSeconds(10)).expiresAt(Instant.now().plusSeconds(60));
    }
    private boolean accepted(Jwt jwt) { return !JwtSecurity.validators("http://issuer.test", "tickets-api").validate(jwt).hasErrors(); }
    @Test void acceptsValidClaims() { assertThat(accepted(valid().build())).isTrue(); }
    @Test void rejectsExpiredWithoutClockGrace() {
        assertThat(accepted(valid().expiresAt(Instant.now().minusSeconds(1)).build())).isFalse();
    }
    @Test void rejectsWrongIssuer() { assertThat(accepted(valid().issuer("http://wrong.test").build())).isFalse(); }
    @Test void rejectsWrongAudience() { assertThat(accepted(valid().audience(List.of("mcp-server")).build())).isFalse(); }
    @Test void rejectsMissingExpiry() {
        assertThat(accepted(valid().claims(c -> c.remove("exp")).build())).isFalse();
    }
    @Test void rejectsIdToken() { assertThat(accepted(valid().claim("typ", "ID").build())).isFalse(); }
    @Test void rejectsFutureNotBefore() {
        assertThat(accepted(valid().notBefore(Instant.now().plusSeconds(30)).build())).isFalse();
    }
    @Test void mapsOnlyAllowlistedRolesOfExactClient() {
        var jwt = valid().claim("resource_access", Map.of("tickets-api", Map.of("roles", List.of("tickets.read", "admin")),
            "other-client", Map.of("roles", List.of("tickets.write"))))
            .claim("realm_access", Map.of("roles", List.of("tickets.write"))).build();
        assertThat(JwtSecurity.roles("tickets-api", List.of("tickets.read", "tickets.write")).convert(jwt))
            .extracting("authority").containsExactly("tickets.read");
    }
    @Test void ignoresMalformedRoles() {
        assertThat(JwtSecurity.roles("tickets-api", List.of("tickets.write"))
            .convert(valid().claim("resource_access", List.of("tickets.write")).build())).isEmpty();
    }
}
