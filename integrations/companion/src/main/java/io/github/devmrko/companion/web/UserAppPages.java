package io.github.devmrko.companion.web;
import io.github.devmrko.companion.adapter.DeliveryEvidence.Scope;
import io.github.devmrko.companion.adapter.UserAppRuntime;
import jakarta.servlet.http.*;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller @Profile("!legacy")
public class UserAppPages {
 private final CatalogPages catalog;private final UserAppRuntime runtime;
 public UserAppPages(CatalogPages catalog,UserAppRuntime runtime){this.catalog=catalog;this.runtime=runtime;}
 private Scope scope(Authentication auth,HttpServletRequest request){
  var c=SecurityConfig.connection(auth);var selection=catalog.selection(c,request.getSession());
  if(request.getSession().getAttribute("scopeInvalid")!=null)throw new IllegalStateException("접속 범위를 확인하세요.");
  return Scope.of(c,selection.region(),selection.compartment());
 }
 @GetMapping("/applications") String page(Authentication auth,HttpServletRequest request,Model model,
       @RequestParam(defaultValue="") String app,@RequestParam(defaultValue="") String version,@RequestParam(defaultValue="runtime") String kind){
  catalog.navigation(auth,request,model);model.addAttribute("scopeBack","/applications");model.addAttribute("apps",List.of());
  try{var s=scope(auth,request);model.addAttribute("apps",runtime.list(s));if(!app.isBlank())model.addAttribute("logText",kind.equals("requests")?runtime.requests(s,app):runtime.logs(s,app,version,kind));}
  catch(IllegalArgumentException|IllegalStateException e){model.addAttribute("message",e.getMessage());}
  return "user-apps";
 }
 @PostMapping("/applications/action") String action(Authentication auth,HttpServletRequest request,RedirectAttributes flash,
       @RequestParam String action,@RequestParam(defaultValue="") String app,@RequestParam(defaultValue="") String version,
       @RequestParam(defaultValue="") String source,@RequestParam(defaultValue="") String message,@RequestParam(defaultValue="false") boolean trusted){
  try{var s=scope(auth,request);
   if(action.equals("register")){if(!trusted)throw new IllegalArgumentException("이 서버에서 실행할 수 있는 신뢰한 코드인지 확인하세요.");runtime.register(s,source);}
   else if(action.equals("invoke"))flash.addFlashAttribute("invocation",runtime.invoke(s,app,message));
   else runtime.action(s,action,app,version);
   flash.addFlashAttribute("message",action.equals("invoke")?"호출 결과에서 성공 여부와 실패 단계를 확인하세요.":"앱 관리 작업을 완료했습니다.");
  }catch(IllegalArgumentException|IllegalStateException e){flash.addFlashAttribute("message",e.getMessage());}
  return "redirect:/applications";
 }
}
