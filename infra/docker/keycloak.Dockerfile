# Pre-built ("optimized") Keycloak: the Quarkus build step runs once at image build instead of at every start.
FROM quay.io/keycloak/keycloak:26.4 AS builder
ENV KC_DB=postgres KC_HEALTH_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.4
COPY --from=builder /opt/keycloak/ /opt/keycloak/
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
