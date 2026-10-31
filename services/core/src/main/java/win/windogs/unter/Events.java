package win.windogs.unter;

import java.util.*;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import com.fasterxml.jackson.databind.ObjectMapper;

@Component
public class Events {
    private final JdbcTemplate db;
    private final RabbitTemplate rabbit;
    private final ObjectMapper json;
    public Events(JdbcTemplate db, RabbitTemplate rabbit,ObjectMapper json) {this.db=db;this.rabbit=rabbit;this.json=json;}
    @Bean public Declarables topology() {
        TopicExchange exchange=new TopicExchange("unter.events",true,false);
        org.springframework.amqp.core.Queue queue=new org.springframework.amqp.core.Queue("unter.activity",true);
        return new Declarables(exchange,queue,BindingBuilder.bind(queue).to(exchange).with("#"));
    }
    @Scheduled(fixedDelay=3000)
    public void publish() {
        try {
            for (Map<String,Object> row:db.queryForList("SELECT * FROM outbox WHERE NOT sent ORDER BY created_at LIMIT 50")) {
                byte[] body=json.writeValueAsBytes(Map.of("id",row.get("id"),"kind",row.get("kind"),"data",json.readTree(row.get("payload").toString())));
                rabbit.invoke(operations -> {
                    operations.send("unter.events",row.get("kind").toString(), MessageBuilder.withBody(body).setContentType("application/json").setDeliveryMode(MessageDeliveryMode.PERSISTENT).build());
                    operations.waitForConfirmsOrDie(5000); return true;
                });
                db.update("UPDATE outbox SET sent=true WHERE id=?",row.get("id"));
            }
        } catch (Exception ignored) { /* Unsent records remain for retry; never log credentials or payloads. */ }
    }
}
