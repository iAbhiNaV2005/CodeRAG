package com.coderag.gateway.config;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

/**
 * Configures the AWS DynamoDB client.
 *
 * On real AWS (EC2): uses the default credential provider chain, which
 * automatically picks up the IAM instance profile attached to the EC2.
 *
 * On local dev: uses static test credentials and a custom endpoint URL
 * pointing at DynamoDB Local or LocalStack.
 */
@Configuration
public class DynamoDbConfig {

    @Value("${aws.region}")
    private String region;

    @Value("${aws.endpoint-url:}")
    private String endpointUrl;

    @Value("${aws.access-key-id:}")
    private String accessKeyId;

    @Value("${aws.secret-access-key:}")
    private String secretAccessKey;

    @Bean
    public DynamoDbClient dynamoDbClient() {
        var builder = DynamoDbClient.builder()
                .region(Region.of(region));

        if (endpointUrl != null && !endpointUrl.isBlank()) {
            // Local development: use static credentials + custom endpoint
            builder.endpointOverride(URI.create(endpointUrl))
                   .credentialsProvider(StaticCredentialsProvider.create(
                           AwsBasicCredentials.create(accessKeyId, secretAccessKey)
                   ));
        } else {
            // Real AWS (EC2): use IAM instance profile via default provider chain
            builder.credentialsProvider(DefaultCredentialsProvider.create());
        }

        return builder.build();
    }
}
