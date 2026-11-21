package com.lizhou.tools;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

import com.mchange.v2.c3p0.ComboPooledDataSource;

public class MysqlTool {
    private static final ComboPooledDataSource dataSource = new ComboPooledDataSource();
    private static final ThreadLocal<Connection> tl = new ThreadLocal<Connection>();

    static {
        String url = System.getProperty("ssms.jdbc.url", System.getenv("SSMS_DB_URL"));
        String user = System.getProperty("ssms.jdbc.user", System.getenv("SSMS_DB_USER"));
        String password = System.getProperty("ssms.jdbc.password", System.getenv("SSMS_DB_PASSWORD"));
        if (url != null) {
            dataSource.setJdbcUrl(url);
        }
        if (user != null) {
            dataSource.setUser(user);
        }
        if (password != null) {
            dataSource.setPassword(password);
        }
        if (dataSource.getPassword() == null || dataSource.getPassword().isEmpty()) {
            throw new IllegalStateException("Set SSMS_DB_PASSWORD or -Dssms.jdbc.password");
        }
    }

    public static DataSource getDataSource() {
        return dataSource;
    }

    public static Connection getConnection() {
        Connection conn = tl.get();
        if (conn == null) {
            try {
                conn = dataSource.getConnection();
                // 保留原 MySQL 事务的可重复读语义。
                conn.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
                tl.set(conn);
            } catch (SQLException e) {
                close(conn);
                throw new IllegalStateException("Cannot acquire database connection", e);
            }
        }
        return conn;
    }

    public static void startTransaction() {
        try {
            getConnection().setAutoCommit(false);
        } catch (SQLException e) {
            throw new IllegalStateException("Cannot start transaction", e);
        }
    }

    public static void rollback() {
        Connection conn = tl.get();
        if (conn == null) {
            return;
        }
        try {
            conn.rollback();
        } catch (SQLException e) {
            throw new IllegalStateException("Cannot roll back transaction", e);
        }
    }

    public static void commit() {
        Connection conn = tl.get();
        if (conn == null) {
            throw new IllegalStateException("No transaction connection");
        }
        try {
            conn.commit();
        } catch (SQLException e) {
            throw new IllegalStateException("Cannot commit transaction", e);
        }
    }

    public static void closeConnection() {
        Connection conn = tl.get();
        tl.remove();
        try {
            if (conn != null && !conn.getAutoCommit()) {
                conn.rollback();
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Cannot reset transaction", e);
        } finally {
            close(conn);
        }
    }

    public static void close(Connection conn) {
        try {
            if (conn != null) {
                conn.close();
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }

    public static void close(Statement stm) {
        try {
            if (stm != null) {
                stm.close();
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }

    public static void close(ResultSet rs) {
        try {
            if (rs != null) {
                rs.close();
            }
        } catch (SQLException e) {
            e.printStackTrace();
        }
    }

}
