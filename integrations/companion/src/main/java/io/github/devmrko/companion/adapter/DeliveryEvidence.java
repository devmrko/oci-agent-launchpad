package io.github.devmrko.companion.adapter;

import io.github.devmrko.companion.domain.Models.Connection;
import java.net.URI;
import java.nio.file.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public class DeliveryEvidence {
    public record Scope(String profile,String tenancy,String user,boolean demo,String region,String compartment) {
        public static Scope of(Connection c,String region,String compartment) {
            return new Scope(c.profile(),c.tenancy(),c.user(),c.demo(),region,compartment);
        }
    }
    public record Stage(String title,String status,String detail,String digest,String url) {}
    public record Entry(Scope scope,String name,String exportedAt,String specText,List<Stage> stages) {}
    public record Document(int schemaVersion,List<Entry> entries) {}
    private final Path file;
    private final JsonMapper mapper=JsonMapper.builder().build();
    public DeliveryEvidence(@Value("${companion.delivery-evidence:.data/delivery-evidence.json}") String file) {
        this.file=Path.of(file);
    }
    public static boolean allowedUrl(String value) {
        if(value==null) return true;
        if(value.equals("/deployments")) return true;
        try {
            URI u=URI.create(value);
            return value.length()<=2048 && ("http".equals(u.getScheme()) || "https".equals(u.getScheme()))
                && u.getHost()!=null && u.getRawUserInfo()==null && u.getRawQuery()==null
                && u.getRawFragment()==null && u.getPort()!=0 && u.getPort()<=65535;
        } catch(IllegalArgumentException e) { return false; }
    }
    public List<Entry> list(Scope scope) {
        try {
            if(Files.isSymbolicLink(file)) throw new IllegalArgumentException();
            if(!Files.exists(file)) return List.of();
            if(Files.size(file)>4_000_000) throw new IllegalArgumentException();
            Document d=mapper.readValue(Files.readString(file),Document.class);
            if(d.schemaVersion()!=1 || d.entries()==null || d.entries().size()>100) throw new IllegalArgumentException();
            for(Entry e:d.entries()) {
                if(e.scope()==null || e.name()==null || e.exportedAt()==null || e.specText()==null
                   || e.specText().length()>16000 || e.stages()==null || e.stages().size()>10) throw new IllegalArgumentException();
                for(Stage s:e.stages()) {
                    if(s.title()==null || s.status()==null || s.detail()==null || !allowedUrl(s.url())
                       || (s.digest()!=null && !s.digest().matches("[a-f0-9]{64}"))) throw new IllegalArgumentException();
                }
            }
            return d.entries().stream().filter(e->e.scope().equals(scope)).toList();
        } catch(Exception e) { throw new IllegalStateException("개발·실행 근거 파일을 읽지 못했습니다. 형식과 설정을 확인하세요.",e); }
    }
}
