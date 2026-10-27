package com.example.mcpdemo.mcp;

import static org.assertj.core.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;

class RegistrationControllerTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test void acceptsProviderNeutralHttpsAndLiteralLoopbackCallbacks() throws Exception {
        for (String uri : List.of("https://claude.ai/api/mcp/auth_callback", "https://gemini.google.com/callback",
            "https://chatgpt.com/connector_platform_oauth_redirect", "https://another-client.example/callback",
            "http://localhost:54213/callback", "http://127.0.0.1:38741/oauth/callback", "http://[::1]:8765/callback"))
            assertThat(RegistrationController.validRedirects(mapper.readTree("{\"redirect_uris\":[\"" + uri + "\"]}")))
                .as(uri).isTrue();
    }

    @Test void rejectsRemoteHttpWildcardsUserInfoFragmentsAndInvalidMetadata() throws Exception {
        for (String uri : List.of("http://claude.ai/callback", "http://192.168.1.2/callback", "https://client.example/*",
            "https://client.example/%2a", "https://user@client.example/callback", "https://client.example/callback#token",
            "custom-app:/callback", "file:///tmp/callback", "http://127.0.0.1.evil.test/callback",
            "https://client.example:99999/callback"))
            assertThat(RegistrationController.validRedirects(mapper.readTree("{\"redirect_uris\":[\"" + uri + "\"]}")))
                .as(uri).isFalse();
        for (String json : List.of("{}", "{\"redirect_uris\":[]}", "{\"redirect_uris\":\"https://client.example/cb\"}",
            "{\"redirect_uris\":[null]}", "{\"redirect_uris\":[\"https://client.example/cb\",\"http://evil.test/cb\"]}"))
            assertThat(RegistrationController.validRedirects(mapper.readTree(json))).as(json).isFalse();
    }
}
