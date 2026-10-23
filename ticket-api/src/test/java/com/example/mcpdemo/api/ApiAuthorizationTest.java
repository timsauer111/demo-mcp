package com.example.mcpdemo.api;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiAuthorizationTest {
    @Autowired MockMvc mvc;
    @Autowired TicketStore store;
    @MockitoBean JwtDecoder decoder;
    private static final String INPUT = "{\"title\":\"Test\",\"description\":\"synthetic\",\"status\":\"OPEN\"}";
    private Jwt token(String client, List<String> roles) {
        return Jwt.withTokenValue("unit-fixture").header("alg", "RS256").subject("user")
            .expiresAt(Instant.now().plusSeconds(60)).claim("resource_access", Map.of(client, Map.of("roles", roles))).build();
    }
    @BeforeEach void setup() {
        store.reset();
        when(decoder.decode("read")).thenReturn(token("tickets-api", List.of("tickets.read")));
        when(decoder.decode("write")).thenReturn(token("tickets-api", List.of("tickets.read", "tickets.write")));
        when(decoder.decode("other")).thenReturn(token("other", List.of("tickets.read", "tickets.write")));
        when(decoder.decode("invalid")).thenThrow(new BadJwtException("invalid"));
    }
    @Test void realWriteEndpointsWorkForAuthorizedUser() throws Exception {
        mvc.perform(post("/tickets").header("Authorization", "Bearer write").contentType(MediaType.APPLICATION_JSON).content(INPUT))
            .andExpect(status().isCreated()).andExpect(jsonPath("$.id").value(4));
        mvc.perform(patch("/tickets/4").header("Authorization", "Bearer write").contentType(MediaType.APPLICATION_JSON)
            .content("{\"status\":\"CLOSED\"}")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("CLOSED"));
        mvc.perform(delete("/tickets/4").header("Authorization", "Bearer write")).andExpect(status().isNoContent());
        assertThat(store.list(null, 0, 100).total()).isEqualTo(3);
    }
    @Test void sameReadTokenCannotCreatePatchDeleteOrReset() throws Exception {
        var before = store.list(null, 0, 100);
        mvc.perform(get("/tickets").header("Authorization", "Bearer read")).andExpect(status().isOk());
        mvc.perform(post("/tickets").header("Authorization", "Bearer read").contentType(MediaType.APPLICATION_JSON).content(INPUT))
            .andExpect(status().isForbidden());
        mvc.perform(patch("/tickets/1").header("Authorization", "Bearer read").contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"changed\"}"))
            .andExpect(status().isForbidden());
        mvc.perform(delete("/tickets/1").header("Authorization", "Bearer read")).andExpect(status().isForbidden());
        mvc.perform(post("/demo/reset").header("Authorization", "Bearer read")).andExpect(status().isForbidden());
        assertThat(store.list(null, 0, 100)).isEqualTo(before);
    }
    @Test void missingAndInvalidTokensAreUnauthorized() throws Exception {
        mvc.perform(get("/tickets")).andExpect(status().isUnauthorized());
        mvc.perform(get("/tickets").header("Authorization", "Bearer invalid")).andExpect(status().isUnauthorized());
    }
    @Test void rolesOfOtherClientsGrantNothing() throws Exception {
        mvc.perform(get("/tickets").header("Authorization", "Bearer other")).andExpect(status().isForbidden());
    }
    @Test void rejectsInvalidPaginationAndPayload() throws Exception {
        mvc.perform(get("/tickets?limit=101").header("Authorization", "Bearer read")).andExpect(status().isBadRequest());
        mvc.perform(post("/tickets").header("Authorization", "Bearer write").contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"\",\"description\":\"x\",\"status\":\"OPEN\"}")).andExpect(status().isBadRequest());
        mvc.perform(patch("/tickets/1").header("Authorization", "Bearer write").contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"   \"}")).andExpect(status().isBadRequest());
    }
}
