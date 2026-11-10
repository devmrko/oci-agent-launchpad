package io.github.devmrko.companion;
import io.github.devmrko.companion.adapter.DeliveryEvidence;
import io.github.devmrko.companion.adapter.DeliveryEvidence.*;
import java.nio.file.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;
class DeliveryEvidenceTest {
 @Test void scopeAndLinksAreChecked() throws Exception {
  Path file=Files.createTempFile("delivery-evidence-",".json");
  try {
   Scope a=new Scope("DEFAULT","t","u",false,"seoul","c");
   Scope b=new Scope("OTHER","t","u",false,"seoul","c");
   Entry entry=new Entry(a,"release","now","## REQ-001",List.of(new Stage("trace","unlinked","none",null,"http://100.65.0.71:18080")));
   var mapper=JsonMapper.builder().build();
   Files.writeString(file,mapper.writeValueAsString(new Document(1,List.of(entry))));
   var registry=new DeliveryEvidence(file.toString());
   assertEquals(1,registry.list(a).size());assertTrue(registry.list(b).isEmpty());
   assertFalse(DeliveryEvidence.allowedUrl("javascript:alert(1)"));
   assertFalse(DeliveryEvidence.allowedUrl("//evil.example"));
   assertFalse(DeliveryEvidence.allowedUrl("https://user:secret@example.com"));
   assertFalse(DeliveryEvidence.allowedUrl("https://example.com/?key=secret"));
   String run="/deployments/runs?pipeline=ocid1.devopsdeploypipeline.oc1.ap-seoul-1.abc&run=ocid1.devopsdeployment.oc1.ap-seoul-1.def";
   assertTrue(DeliveryEvidence.allowedUrl(run));
   assertFalse(DeliveryEvidence.allowedUrl(run+"&redirect=https://evil.example"));
   assertFalse(DeliveryEvidence.allowedUrl(run.replace("def","def%26evil")));
   assertFalse(DeliveryEvidence.allowedUrl("/deployments/runs?run=other"));
   Files.writeString(file,"{}");assertThrows(IllegalStateException.class,()->registry.list(a));
  } finally {Files.deleteIfExists(file);}
 }
}
