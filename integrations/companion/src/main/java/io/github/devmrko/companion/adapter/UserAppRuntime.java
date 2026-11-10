package io.github.devmrko.companion.adapter;
import io.github.devmrko.companion.adapter.DeliveryEvidence.Scope;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public class UserAppRuntime {
 public record App(String id,List<String> versions,String version,String status,String previous,Integer port,Long pid,String url) {}
 private final Path state,scopeFile;
 private final JsonMapper mapper=JsonMapper.builder().build();
 private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).followRedirects(HttpClient.Redirect.NEVER).build();
 public UserAppRuntime(@Value("${companion.user-app-state:.data/user-apps}") String state,
                       @Value("${companion.user-app-scope:.data/user-app-scope.json}") String scopeFile) {
  this.state=Path.of(state);this.scopeFile=Path.of(scopeFile);
 }
 private String request(Scope scope,Map<String,Object> command) {
  try {
   if(!scope.equals(mapper.readValue(Files.readString(scopeFile),Scope.class)))throw new IllegalArgumentException();
   String base=mapper.readTree(Files.readString(state.resolve("connection.json"))).path("url").asText();
   URI uri=URI.create(base);
   if(!"http".equals(uri.getScheme())||!"127.0.0.1".equals(uri.getHost())||uri.getPort()<1024||uri.getPort()>65535
      ||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||!uri.getPath().isEmpty())throw new IllegalArgumentException();
   String token=Files.readString(state.resolve("operator-token"));
   if(!token.matches("[A-Za-z0-9_-]{32,128}"))throw new IllegalArgumentException();
   var builder=HttpRequest.newBuilder(URI.create(base+(command==null?"/apps":"/command")))
      .timeout(Duration.ofSeconds(140)).header("Authorization","Bearer "+token);
   if(command!=null)builder.header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(command)));
   var response=client.send(builder.build(),HttpResponse.BodyHandlers.ofString());
   if(response.statusCode()!=200||response.body().length()>1000000)throw new IllegalArgumentException();
   return response.body();
  }catch(Exception e){throw new IllegalStateException("앱 관리 요청을 완료하지 못했습니다. 접속 범위·관리 서버·빌드/실행 로그를 확인하세요.");}
 }
 public List<App> list(Scope scope){return Arrays.asList(mapper.readValue(request(scope,null),App[].class));}
 public void register(Scope scope,String source){
  if(source.isBlank()||source.length()>2048||!Path.of(source).isAbsolute())throw new IllegalArgumentException("서버의 프로젝트 절대 경로를 입력하세요.");
  request(scope,Map.of("action","register","source",source));
 }
 public void action(Scope scope,String action,String app,String version){
  if(!Set.of("deploy","rollback","stop").contains(action)||!app.matches("[a-z][a-z0-9-]{0,47}"))throw new IllegalArgumentException("앱과 동작을 확인하세요.");
  var data=new LinkedHashMap<String,Object>();data.put("action",action);data.put("app",app);
  if(action.equals("deploy")){if(!version.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}"))throw new IllegalArgumentException("버전을 선택하세요.");data.put("version",version);}
  request(scope,data);
 }
 public String invoke(Scope scope,String app,String message){
  if(!app.matches("[a-z][a-z0-9-]{0,47}")||message.isBlank()||message.length()>1000)throw new IllegalArgumentException("앱과 1~1000자 메시지를 확인하세요.");
  return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(mapper.readTree(request(scope,Map.of("action","invoke","app",app,"payload",Map.of("message",message)))));
 }
 public String requests(Scope scope,String app){
  if(!app.matches("[a-z][a-z0-9-]{0,47}"))throw new IllegalArgumentException("앱을 확인하세요.");
  return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(mapper.readTree(request(scope,Map.of("action","requests","app",app))));
 }
 public String logs(Scope scope,String app,String version,String kind){
  if(!app.matches("[a-z][a-z0-9-]{0,47}")||!version.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")||!Set.of("build","runtime").contains(kind))throw new IllegalArgumentException("로그 대상을 확인하세요.");
  return mapper.readTree(request(scope,Map.of("action","logs","app",app,"version",version,"kind",kind))).path("tail").asText();
 }
}
