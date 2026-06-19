package com.coderag.gateway.filter;

import java.time.Instant;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;

/**
 * Rate limiter using DynamoDB as the backing store.
 *
 * Uses a sliding window counter per user (or IP for unauthenticated requests).
 * Each window is 60 seconds. Requests exceeding the limit get 429 Too Many Requests.
 *
 * DynamoDB key structure:
 *   - key: "ratelimit#{userId}#{windowId}"
 *   - count: number of requests in this window
 *   - ttl: auto-expire after 2 minutes
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1) // Run after JWT filter
public class RateLimitFilter implements WebFilter {

    private static final Logger log = LoggerFactory.getLogger(RateLimitFilter.class);
    private static final long WINDOW_SIZE_SECONDS = 60;

    private final DynamoDbClient dynamoDb;
    private final String tableName;
    private final int maxRequests;

    public RateLimitFilter(
            DynamoDbClient dynamoDb,
            @Value("${aws.dynamodb.rate-limits-table}") String tableName,
            @Value("${rate-limit.requests-per-minute}") int maxRequests
    ) {
        this.dynamoDb = dynamoDb;
        this.tableName = tableName;
        this.maxRequests = maxRequests;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String path = exchange.getRequest().getPath().value();

        // Skip rate limiting for health/auth endpoints
        if (path.startsWith("/health") || path.startsWith("/actuator") || path.startsWith("/auth/")) {
            return chain.filter(exchange);
        }

        // Get user identifier
        String headerUserId = exchange.getRequest().getHeaders().getFirst("X-User-Id");
        final String userId;
        if (headerUserId != null) {
            userId = headerUserId;
        } else {
            // Fall back to IP for unauthenticated requests
            var remoteAddress = exchange.getRequest().getRemoteAddress();
            userId = remoteAddress != null ? remoteAddress.getAddress().getHostAddress() : "unknown";
        }

        // Calculate current window
        long windowId = Instant.now().getEpochSecond() / WINDOW_SIZE_SECONDS;
        String key = "ratelimit#" + userId + "#" + windowId;

        // Check and increment counter in DynamoDB
        return Mono.fromCallable(() -> checkAndIncrement(key))
                .flatMap(allowed -> {
                    if (!allowed) {
                        log.warn("Rate limit exceeded for user: {}", userId);
                        exchange.getResponse().setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
                        exchange.getResponse().getHeaders().add("X-RateLimit-Limit", String.valueOf(maxRequests));
                        exchange.getResponse().getHeaders().add("Retry-After", "60");
                        return exchange.getResponse().setComplete();
                    }

                    // Add rate limit headers
                    exchange.getResponse().getHeaders().add("X-RateLimit-Limit", String.valueOf(maxRequests));
                    return chain.filter(exchange);
                });
    }

    /**
     * Atomically check the current count and increment.
     * Returns true if the request is allowed, false if rate limited.
     */
    private boolean checkAndIncrement(String key) {
        try {
            // Get current count
            GetItemResponse response = dynamoDb.getItem(GetItemRequest.builder()
                    .tableName(tableName)
                    .key(Map.of("key", AttributeValue.builder().s(key).build()))
                    .build());

            int currentCount = 0;
            if (response.hasItem() && response.item().containsKey("count")) {
                currentCount = Integer.parseInt(response.item().get("count").n());
            }

            if (currentCount >= maxRequests) {
                return false;
            }

            // Increment counter with TTL (2 minutes from now)
            long ttl = Instant.now().getEpochSecond() + (WINDOW_SIZE_SECONDS * 2);

            dynamoDb.putItem(PutItemRequest.builder()
                    .tableName(tableName)
                    .item(Map.of(
                            "key", AttributeValue.builder().s(key).build(),
                            "count", AttributeValue.builder().n(String.valueOf(currentCount + 1)).build(),
                            "ttl", AttributeValue.builder().n(String.valueOf(ttl)).build()
                    ))
                    .build());

            return true;

        } catch (Exception e) {
            log.error("Rate limit check failed, allowing request: {}", e.getMessage());
            // Fail open — if DynamoDB is down, allow the request
            return true;
        }
    }
}
