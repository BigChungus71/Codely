class ReviewJava {
    void review(java.sql.Connection connection, String name) throws Exception {
        try (var statement = connection.prepareStatement("SELECT name FROM accounts WHERE name = ?")) {
            statement.setString(1, name);
            statement.executeQuery();
        }
        java.security.MessageDigest.getInstance("SHA-256");
    }
}
