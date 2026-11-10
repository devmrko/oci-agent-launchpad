package io.github.devmrko.companion;
import io.github.devmrko.companion.adapter.DeliveryEvidence;
import io.github.devmrko.companion.adapter.DeliveryEvidence.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpSession;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.hamcrest.Matchers.*;
@SpringBootTest @ActiveProfiles("demo") @AutoConfigureMockMvc
class DeliveryEvidenceWebTest {
 @Autowired MockMvc mvc;
 @MockitoBean DeliveryEvidence evidence;
 @Test void authenticationAndEscaping() throws Exception {
  mvc.perform(get("/delivery/evidence")).andExpect(redirectedUrl("/login"));
  verifyNoInteractions(evidence);
  var session=(MockHttpSession)mvc.perform(post("/connect").with(csrf()).param("profile","DEMO")).andReturn().getRequest().getSession(false);
  when(evidence.list(any())).thenReturn(List.of(new Entry(null,"<script>alert(1)</script>","now","<b>spec</b>",List.of(new Stage("Langfuse","미연결","trace 없음",null,null)))));
  mvc.perform(get("/delivery/evidence").session(session)).andExpect(status().isOk())
   .andExpect(content().string(containsString("&lt;script&gt;")))
   .andExpect(content().string(not(containsString("<script>alert(1)</script>"))))
   .andExpect(content().string(containsString("미연결")));
  when(evidence.list(any())).thenThrow(new IllegalStateException());
  mvc.perform(get("/delivery/evidence").session(session)).andExpect(status().isOk())
   .andExpect(content().string(containsString("근거를 읽지 못했습니다")));
 }
}
