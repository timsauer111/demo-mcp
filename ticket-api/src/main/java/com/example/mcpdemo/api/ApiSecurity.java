package com.example.mcpdemo.api;

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
class ApiSecurity {
    @Bean JwtDecoder jwtDecoder(@Value("${demo.issuer}") String issuer) {
        return JwtSecurity.decoder(issuer, "tickets-api");
    }

    @Bean SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/health", "/openapi.yaml").permitAll()
                .requestMatchers(HttpMethod.GET, "/tickets", "/tickets/*").hasAuthority("tickets.read")
                .requestMatchers(HttpMethod.POST, "/tickets", "/demo/reset").hasAuthority("tickets.write")
                .requestMatchers(HttpMethod.PATCH, "/tickets/*").hasAuthority("tickets.write")
                .requestMatchers(HttpMethod.DELETE, "/tickets/*").hasAuthority("tickets.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(j -> j.jwtAuthenticationConverter(
                JwtSecurity.authentication("tickets-api", List.of("tickets.read", "tickets.write"))))
                .authenticationEntryPoint((req, res, ex) -> {
                    res.setHeader("WWW-Authenticate", "Bearer"); res.setStatus(401);
                }).accessDeniedHandler((req, res, ex) -> res.setStatus(403)))
            .build();
    }
}
