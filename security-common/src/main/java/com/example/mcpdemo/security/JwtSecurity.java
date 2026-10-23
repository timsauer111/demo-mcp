package com.example.mcpdemo.security;

import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

/** Explicit client-role mapping: realm roles and roles of other clients grant nothing. */
public final class JwtSecurity {
    private JwtSecurity() {}

    public static JwtDecoder decoder(String issuer, String audience) {
        var decoder = NimbusJwtDecoder.withJwkSetUri(issuer + "/protocol/openid-connect/certs").build();
        decoder.setJwtValidator(validators(issuer, audience));
        return decoder;
    }

    public static OAuth2TokenValidator<Jwt> validators(String issuer, String audience) {
        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> jwt.getAudience().contains(audience)
            ? OAuth2TokenValidatorResult.success() : invalid();
        OAuth2TokenValidator<Jwt> requiredClaims = jwt -> jwt.getExpiresAt() != null
            && jwt.getSubject() != null && "Bearer".equals(jwt.getClaimAsString("typ"))
            ? OAuth2TokenValidatorResult.success() : invalid();
        return new DelegatingOAuth2TokenValidator<>(new JwtTimestampValidator(Duration.ZERO),
            new JwtIssuerValidator(issuer), audienceValidator, requiredClaims);
    }

    private static OAuth2TokenValidatorResult invalid() {
        return OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token", "Token not accepted", null));
    }

    public static JwtAuthenticationConverter authentication(String client, Collection<String> allowed) {
        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(roles(client, allowed));
        converter.setPrincipalClaimName("sub");
        return converter;
    }

    public static Converter<Jwt, Collection<GrantedAuthority>> roles(String client, Collection<String> allowed) {
        return jwt -> {
            Object access = jwt.getClaims().get("resource_access");
            if (!(access instanceof Map<?, ?> clients) || !(clients.get(client) instanceof Map<?, ?> entry)
                || !(entry.get("roles") instanceof Collection<?> values)) return List.of();
            return values.stream().filter(String.class::isInstance).map(String.class::cast)
                .filter(allowed::contains).<GrantedAuthority>map(SimpleGrantedAuthority::new).toList();
        };
    }
}
