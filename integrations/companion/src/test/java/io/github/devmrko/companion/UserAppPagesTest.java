package io.github.devmrko.companion;
import io.github.devmrko.companion.adapter.UserAppRuntime;
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
class UserAppPagesTest {
 @Autowired MockMvc mvc;
 @MockitoBean UserAppRuntime runtime;
 @Test void operatorWorkflowRequiresLoginCsrfAndTrustedSource() throws Exception {
  mvc.perform(get("/applications")).andExpect(redirectedUrl("/login"));verifyNoInteractions(runtime);
  var session=(MockHttpSession)mvc.perform(post("/connect").with(csrf()).param("profile","DEMO")).andReturn().getRequest().getSession(false);
  when(runtime.list(any())).thenReturn(List.of(new UserAppRuntime.App("user-python",List.of("v1","v2"),"v2","UP","v1",32100,123L,"http://127.0.0.1:32100"),new UserAppRuntime.App("user-java",List.of("v1"),"v1","UP",null,32101,124L,"http://127.0.0.1:32101")));
  mvc.perform(get("/applications").session(session)).andExpect(status().isOk()).andExpect(content().string(containsString("user-python"))).andExpect(content().string(containsString("user-java"))).andExpect(content().string(containsString("이전 정상 버전 복구")));
  mvc.perform(post("/applications/action").session(session).param("action","deploy").param("app","user-python").param("version","v2")).andExpect(status().isForbidden());
  verify(runtime,never()).action(any(),any(),any(),any());
  mvc.perform(post("/applications/action").with(csrf()).session(session).param("action","register").param("source","/source")).andExpect(redirectedUrl("/applications"));
  verify(runtime,never()).register(any(),any());
  mvc.perform(post("/applications/action").with(csrf()).session(session).param("action","register").param("source","/source").param("trusted","true")).andExpect(redirectedUrl("/applications"));
  verify(runtime).register(any(),eq("/source"));
  mvc.perform(post("/applications/action").with(csrf()).session(session).param("action","rollback").param("app","user-python")).andExpect(redirectedUrl("/applications"));
  verify(runtime).action(any(),eq("rollback"),eq("user-python"),eq(""));
  when(runtime.logs(any(),any(),any(),any())).thenReturn("<script>secret()</script>");
  mvc.perform(get("/applications").session(session).param("app","user-python").param("version","v1")).andExpect(status().isOk()).andExpect(content().string(containsString("&lt;script&gt;"))).andExpect(content().string(not(containsString("<script>secret()"))));
 }
 @Test void invocationRequiresCsrfAndEscapesResults() throws Exception {
  var session=(MockHttpSession)mvc.perform(post("/connect").with(csrf()).param("profile","DEMO")).andReturn().getRequest().getSession(false);
  mvc.perform(post("/applications/action").session(session).param("action","invoke").param("app","connected-agent").param("message","6 times 7")).andExpect(status().isForbidden());
  verify(runtime,never()).invoke(any(),any(),any());
  when(runtime.invoke(any(),eq("connected-agent"),eq("6 times 7"))).thenReturn("<script>result</script>");
  var result=mvc.perform(post("/applications/action").with(csrf()).session(session).param("action","invoke").param("app","connected-agent").param("message","6 times 7")).andExpect(redirectedUrl("/applications")).andReturn();
  verify(runtime).invoke(any(),eq("connected-agent"),eq("6 times 7"));
  when(runtime.list(any())).thenReturn(List.of());
  mvc.perform(get("/applications").session(session).flashAttrs(result.getFlashMap())).andExpect(content().string(containsString("&lt;script&gt;result&lt;/script&gt;")));
  when(runtime.requests(any(),eq("connected-agent"))).thenReturn("[{status:FAILED, error:MCP_FAILED}]");
  mvc.perform(get("/applications").session(session).param("app","connected-agent").param("kind","requests")).andExpect(content().string(containsString("MCP_FAILED")));
 }
 @Test void wrongScopeIsRejectedBeforeTransport() throws Exception {
  var dir=java.nio.file.Files.createTempDirectory("app-scope-");
  try {
   var file=dir.resolve("scope.json");java.nio.file.Files.writeString(file,"{\"profile\":\"A\",\"tenancy\":\"t\",\"user\":\"u\",\"demo\":false,\"region\":\"r\",\"compartment\":\"c\"}");
   var adapter=new UserAppRuntime(dir.toString(),file.toString());
   org.junit.jupiter.api.Assertions.assertThrows(IllegalStateException.class,()->adapter.list(new io.github.devmrko.companion.adapter.DeliveryEvidence.Scope("B","t","u",false,"r","c")));
   java.nio.file.Files.delete(file);
  } finally {java.nio.file.Files.delete(dir);}
 }
}
