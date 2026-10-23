package com.example.mcpdemo.mcp;

import com.example.mcpdemo.security.JwtSecurity;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class McpSecurity {
    static final String RESOURCE = "http://localhost:8082/mcp";
    static final String METADATA = "http://localhost:8082/.well-known/oauth-protected-resource/mcp";
    static final String CHALLENGE = "Bearer resource_metadata=\"" + METADATA + "\", scope=\"mcp.access\"";
    @Bean JwtDecoder jwtDecoder(@Value("${demo.issuer}") String issuer) {
        return JwtSecurity.decoder(issuer, RESOURCE);
    }
    @Bean SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/health", "/.well-known/oauth-protected-resource",
                    "/.well-known/oauth-protected-resource/mcp").permitAll()
                .requestMatchers("/mcp").hasAuthority("mcp.access")
                .anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(j -> j.jwtAuthenticationConverter(
                JwtSecurity.authentication("mcp-server", List.of("mcp.access"))))
                .authenticationEntryPoint((req, res, ex) -> {
                    res.setHeader("WWW-Authenticate", CHALLENGE); res.setStatus(401);
                }).accessDeniedHandler((req, res, ex) -> {
                    res.setHeader("WWW-Authenticate", CHALLENGE + ", error=\"insufficient_scope\"");
                    res.setStatus(403);
                }))
            .build();
    }
}
