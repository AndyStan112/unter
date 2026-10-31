FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY services/core/pom.xml .
RUN mvn -q dependency:go-offline
COPY services/core/src ./src
RUN mvn -q package
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /build/target/unter-core-0.1.0.jar /app/app.jar
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70"
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
