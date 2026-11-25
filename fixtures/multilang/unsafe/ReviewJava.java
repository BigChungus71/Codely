// Static fixture only. Do not execute.
class ReviewJava {
    void review(java.sql.Statement statement, String name) throws Exception {
        statement.executeQuery("SELECT name FROM accounts WHERE name = " + name);
        java.security.MessageDigest.getInstance("MD5");
    }
}
