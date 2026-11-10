package io.github.devmrko.companion.web;

import io.github.devmrko.companion.adapter.DeliveryEvidence;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller @Profile("!legacy")
public class DeliveryEvidencePages {
    private final CatalogPages catalog;
    private final DeliveryEvidence evidence;
    public DeliveryEvidencePages(CatalogPages catalog,DeliveryEvidence evidence) {
        this.catalog=catalog;this.evidence=evidence;
    }
    @GetMapping("/delivery/evidence") String page(Authentication auth,HttpServletRequest request,Model model) {
        var connection=SecurityConfig.connection(auth);
        catalog.navigation(auth,request,model);
        model.addAttribute("connection",connection);
        model.addAttribute("scopeBack","/delivery/evidence");
        model.addAttribute("entries",List.of());
        try {
            var selection=catalog.selection(connection,request.getSession());
            model.addAttribute("selection",selection);
            if(request.getSession().getAttribute("scopeInvalid")==null)
                model.addAttribute("entries",evidence.list(DeliveryEvidence.Scope.of(connection,selection.region(),selection.compartment())));
        } catch(IllegalStateException e) {
            model.addAttribute("message","개발·실행 근거를 읽지 못했습니다. 연결 범위와 근거 파일 설정을 확인하세요.");
        }
        return "delivery-evidence";
    }
}
