package com.example.mcpdemo.mcp;

import com.example.mcpdemo.security.JwtSecurity;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class McpSecurity {
    @Bean @Order(1)
    SecurityFilterChain registrationSecurity(HttpSecurity http) throws Exception {
        // Registration access tokens belong to Keycloak, not to the MCP JWT audience.
        return http.securityMatcher(RegistrationController.PATH, RegistrationController.PATH + "/*")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(a -> a.anyRequest().permitAll()).build();
    }
    @Bean JwtDecoder jwtDecoder(@Value("${demo.issuer}") String issuer, McpEndpoint endpoint) {
        return JwtSecurity.decoder(issuer, endpoint.resource());
    }
    @Bean SecurityFilterChain security(HttpSecurity http, McpEndpoint endpoint) throws Exception {
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
                    res.setHeader("WWW-Authenticate", endpoint.challenge()); res.setStatus(401);
                }).accessDeniedHandler((req, res, ex) -> {
                    res.setHeader("WWW-Authenticate", endpoint.challenge() + ", error=\"insufficient_scope\"");
                    res.setStatus(403);
                }))
            .build();
    }
}
