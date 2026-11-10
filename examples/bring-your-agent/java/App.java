import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

/** User-owned business logic example; no Launchpad or Foundation dependency. */
public class App {
    public static void main(String[] args) throws Exception {
        var host=System.getenv().getOrDefault("BIND_HOST","127.0.0.1");
        var version=System.getenv().getOrDefault("APP_VERSION","unknown");
        var server=HttpServer.create(new InetSocketAddress(host,Integer.parseInt(args[0])),0);
        for(var path:new String[]{"/ready","/answer"}) {
            server.createContext(path,exchange->{
                var text=exchange.getRequestURI().getPath().equals("/ready")?"ready":"java "+version+" result=42";
                var body=text.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200,body.length);
                try(var out=exchange.getResponseBody()){out.write(body);}
                System.out.println("GET "+exchange.getRequestURI().getPath());
            });
        }
        server.start();System.out.println("Java user app started "+version);
    }
}
