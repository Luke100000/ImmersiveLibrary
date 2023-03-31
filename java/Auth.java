import java.awt.*;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.SecureRandom;
import java.util.Arrays;

public class Auth {
    static SecureRandom random = new SecureRandom();

    private static String getToken() {
        byte[] bytes = new byte[64];
        random.nextBytes(bytes);
        return Arrays.toString(bytes);
    }

    private static String read(String path) throws IOException {
        return new String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8);
    }

    private static void write(String path, String content) throws IOException {
        BufferedWriter writer = new BufferedWriter(new FileWriter(path));
        writer.write(content);
        writer.close();
    }

    private static void openAuthentication() {
        try {
            String tmpdir = Files.createTempDirectory("immersive_library").toFile().getAbsolutePath();

            // The unique, private token used to authenticate once authorized
            String token = getToken();

            // Inject token into request
            String content = read("res/page.html");
            content = content.replace("{TOKEN}", token);
            write(tmpdir + "/page.html", content);

            // Copy CSS
            write(tmpdir + "/style.css", read("res/style.css"));

            // Open the authorization URL in the user's default web browser
            Desktop.getDesktop().browse((new File(tmpdir + "/page.html")).toURI());
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    public static void main(String[] args) {
        openAuthentication();
    }
}