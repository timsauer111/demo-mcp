package com.example.mcpdemo.mcp;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.assertj.core.api.Assertions.*;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "demo.client-secret=nonfunctional-unit-fixture")
@AutoConfigureMockMvc
class McpSecurityTest {
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder decoder;
    @MockitoBean TokenExchange exchange;
    private Jwt token(List<String> roles) {
        return Jwt.withTokenValue("unit-fixture").header("alg", "RS256").subject("user")
            .expiresAt(Instant.now().plusSeconds(60)).claim("resource_access", Map.of("mcp-server", Map.of("roles", roles))).build();
    }
    @BeforeEach void setup() {
        when(decoder.decode("valid")).thenReturn(token(List.of("mcp.access")));
        when(decoder.decode("no-role")).thenReturn(token(List.of()));
        when(decoder.decode("invalid")).thenThrow(new BadJwtException("invalid"));
    }
    @Test void challengesEveryTransportMethodWithoutAuthentication() throws Exception {
        for (var req : List.of(post("/mcp"), get("/mcp"), delete("/mcp"))) {
            mvc.perform(req).andExpect(status().isUnauthorized()).andExpect(header().string("WWW-Authenticate", McpSecurity.CHALLENGE));
        }
    }
    @Test void publishesBoundResourceMetadata() throws Exception {
        mvc.perform(get("/.well-known/oauth-protected-resource/mcp")).andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value(McpSecurity.RESOURCE))
            .andExpect(jsonPath("$.scopes_supported[0]").value("mcp.access"));
    }
    @Test void rejectsMissingRoleAndInvalidToken() throws Exception {
        mvc.perform(post("/mcp").header("Authorization", "Bearer no-role")).andExpect(status().isForbidden());
        mvc.perform(post("/mcp").header("Authorization", "Bearer invalid")).andExpect(status().isUnauthorized());
    }
    @Test void rejectsHostAndOriginAttacks() throws Exception {
        mvc.perform(post("/mcp").header("Authorization", "Bearer valid").with(r -> { r.setServerName("attacker.test"); return r; })).andExpect(status().isBadRequest());
        mvc.perform(post("/mcp").header("Authorization", "Bearer valid").header("Origin", "https://attacker.test")).andExpect(status().isForbidden());
    }
    @Test void validatesIntegerArgumentsWithoutTruncation() {
        assertThatThrownBy(() -> TicketTools.integer(1.2, 1, 100)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> TicketTools.integer("1", 1, 100)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> TicketTools.integer(101, 1, 100)).isInstanceOf(IllegalArgumentException.class);
        assertThat(TicketTools.integer(20, 1, 100)).isEqualTo(20);
    }
    @Test void sensitiveContextHasRedactedStringRepresentation() {
        assertThat(new TokenExchange.Subject("sensitive", "user").toString()).doesNotContain("sensitive");
        assertThat(new TokenExchange.TokenResponse("sensitive").toString()).doesNotContain("sensitive");
    }
}
