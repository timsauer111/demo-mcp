package com.example.mcpdemo.mcp;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {"demo.client-secret=nonfunctional-unit-fixture", "demo.resource=https://tickets.example.test/mcp"})
@AutoConfigureMockMvc
class HostedMcpSecurityTest {
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder decoder;
    @MockitoBean TokenExchange exchange;

    @Test void discoveryAndChallengeUseTheConfiguredPublicResource() throws Exception {
        mvc.perform(get("/.well-known/oauth-protected-resource/mcp").with(r -> {
            r.setServerName("tickets.example.test"); return r;
        })).andExpect(status().isOk()).andExpect(jsonPath("$.resource").value("https://tickets.example.test/mcp"));
        mvc.perform(post("/mcp").with(r -> { r.setServerName("tickets.example.test"); return r; }))
            .andExpect(status().isUnauthorized()).andExpect(header().string("WWW-Authenticate",
                "Bearer resource_metadata=\"https://tickets.example.test/.well-known/oauth-protected-resource/mcp\", scope=\"mcp.access\""));
    }

    @Test void publicModeRejectsLoopbackAndForeignOriginsEvenWithValidAuthentication() throws Exception {
        when(decoder.decode("valid")).thenReturn(Jwt.withTokenValue("fixture").header("alg", "RS256")
            .subject("user").expiresAt(Instant.now().plusSeconds(60))
            .claim("resource_access", Map.of("mcp-server", Map.of("roles", List.of("mcp.access")))).build());
        mvc.perform(get("/health").header("Authorization", "Bearer valid"))
            .andExpect(status().isBadRequest());
        mvc.perform(get("/health").header("Authorization", "Bearer valid")
            .header("Origin", "https://attacker.test").with(r -> { r.setServerName("tickets.example.test"); return r; }))
            .andExpect(status().isForbidden());
        mvc.perform(get("/health").header("Authorization", "Bearer valid")
            .header("Origin", "https://tickets.example.test").with(r -> { r.setServerName("tickets.example.test"); return r; }))
            .andExpect(status().isOk());
    }

    @Test void insecureOrAmbiguousResourcesFailAtStartup() {
        for (String resource : List.of("http://public.example/mcp", "https://user@public.example/mcp",
            "https://public.example/mcp?x=y", "https://public.example/mcp#x", "https://public.example/other")) {
            assertThatThrownBy(() -> new McpEndpoint(resource)).isInstanceOf(IllegalArgumentException.class);
        }
        var local = new McpEndpoint("http://localhost:8082/mcp");
        assertThat(local.acceptsHost("localhost")).isTrue();
        assertThat(local.acceptsOrigin("http://127.0.0.1:8082")).isTrue();
        var hosted = new McpEndpoint("https://tickets.example.test/mcp");
        assertThat(hosted.acceptsHost("localhost")).isFalse();
        assertThat(hosted.acceptsOrigin("http://localhost:8082")).isFalse();
    }

    @Test void registrationAccessTokenIsNotInterpretedAsAnMcpToken() throws Exception {
        mvc.perform(post(RegistrationController.PATH).contentType("application/json")
            .content("{\"redirect_uris\":[\"http://remote.example/callback\"]}")
            .header("Authorization", "Bearer registration-token")
            .with(r -> { r.setServerName("tickets.example.test"); return r; }))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error").value("invalid_redirect_uri"));
        verifyNoInteractions(decoder);
    }
}
