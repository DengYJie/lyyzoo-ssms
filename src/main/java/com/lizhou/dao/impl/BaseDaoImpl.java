package com.lizhou.dao.impl;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedList;
import java.util.List;

import org.apache.commons.dbutils.QueryRunner;
import org.apache.commons.dbutils.handlers.BeanHandler;
import org.apache.commons.dbutils.handlers.BeanListHandler;
import org.apache.commons.dbutils.handlers.ScalarHandler;
import com.lizhou.dao.inter.BaseDaoInter;
import com.lizhou.tools.MysqlTool;

/**
 * 基础Dao层
 * @author bojiangzhou
 *
 */
@SuppressWarnings("unchecked")
public class BaseDaoImpl implements BaseDaoInter {

    public List<Object> getList(Class type, String sql) {
        QueryRunner qr = new QueryRunner(MysqlTool.getDataSource());
        List<Object> list;
        try {
            list = qr.query(sql, new BeanListHandler<Object>(type));
        } catch (SQLException e) {
            throw new IllegalStateException("Database query failed", e);
        }
        return list;
    }

    public List<Object> getList(Class type, String sql, Object[] param) {
        QueryRunner qr = new QueryRunner(MysqlTool.getDataSource());
        List<Object> list;
        try {
            list = qr.query(sql, new BeanListHandler<Object>(type), param);
        } catch (SQLException e) {
            throw new IllegalStateException("Database query failed", e);
        }
        return list;
    }

    public List<Object> getList(Class type, String sql, List<Object> param) {
        Object[] params = new Object[param.size()];
        for (int i = 0; i < param.size(); i++) {
            params[i] = param.get(i);
        }
        return getList(type, sql, params);
    }

    public List<Object> getList(Connection conn, Class type, String sql) {
        QueryRunner qr = new QueryRunner();
        List<Object> list = new LinkedList<>();
        try {
            list = qr.query(conn, sql, new BeanListHandler<Object>(type));
        } catch (SQLException e) {
            throw new IllegalStateException("Transaction query failed", e);
        }
        return list;
    }

    public List<Object> getList(Connection conn, Class type, String sql, Object[] param) {
        QueryRunner qr = new QueryRunner();
        List<Object> list = new LinkedList<>();
        try {
            list = qr.query(conn, sql, new BeanListHandler<Object>(type), param);
        } catch (SQLException e) {
            throw new IllegalStateException("Transaction query failed", e);
        }
        return list;
    }

    public List<Object> getList(Connection conn, Class type, String sql, List<Object> param) {
        Object[] params = new Object[param.size()];
        for (int i = 0; i < param.size(); i++) {
            params[i] = param.get(i);
        }
        return getList(conn, type, sql, params);
    }

    public Object getObject(Class type, String sql, Object[] param) {
        QueryRunner qr = new QueryRunner(MysqlTool.getDataSource());
        Object obj = new LinkedList<>();
        try {
            obj = qr.query(sql, new BeanHandler(type), param);
        } catch (SQLException e) {
            throw new IllegalStateException("Database query failed", e);
        }
        return obj;
    }

    public Object getObject(Connection conn, Class type, String sql, Object[] param) {
        QueryRunner qr = new QueryRunner();
        Object obj = new LinkedList<>();
        try {
            obj = qr.query(conn, sql, new BeanHandler(type), param);
        } catch (SQLException e) {
            throw new IllegalStateException("Transaction query failed", e);
        }
        return obj;
    }

    public Long count(String sql) {
        QueryRunner qr = new QueryRunner(MysqlTool.getDataSource());
        Long count = 0L;
        try {
            count = qr.query(sql, new ScalarHandler<Long>());
        } catch (SQLException e) {
            throw new IllegalStateException("Database count failed", e);
        }
        return count;
    }

    public Long count(String sql, Object[] param) {
        QueryRunner qr = new QueryRunner(MysqlTool.getDataSource());
        Long count = 0L;
        try {
            count = qr.query(sql, new ScalarHandler<Long>(), param);
        } catch (SQLException e) {
            throw new IllegalStateException("Database count failed", e);
        }
        return count;
    }

    public Long count(String sql, List<Object> param) {
        //将集合中的参数封装到数组对象中
        Object[] params = new Object[param.size()];
        for (int i = 0; i < param.size(); i++) {
            params[i] = param.get(i);
        }
        return count(sql, params);
    }

    public void update(String sql, Object[] param) {
        QueryRunner qr = new QueryRunner(MysqlTool.getDataSource());
        try {
            qr.update(sql, param);
        } catch (SQLException e) {
            throw new IllegalStateException("Database update failed", e);
        }
    }

    public void update(String sql, List<Object> param) {
        Object[] params = new Object[param.size()];
        for (int i = 0; i < param.size(); i++) {
            params[i] = param.get(i);
        }
        update(sql, params);
    }

    public void updateTransaction(Connection conn, String sql, Object[] param) throws SQLException {
        QueryRunner qr = new QueryRunner();
        qr.update(conn, sql, param);
    }

    public void updateBatch(String sql, Object[][] param) {
        insertBatch(sql, param);
    }

    public void insert(String sql, Object[] param) {
        update(sql, param);
    }

    public void insertTransaction(Connection conn, String sql, Object[] param) throws SQLException {
        updateTransaction(conn, sql, param);
    }

    public int insertReturnKeys(String sql, Object[] param) {
        try (Connection conn = MysqlTool.getDataSource().getConnection()) {
            return insertReturnKeysTransaction(conn, sql, param);
        } catch (SQLException e) {
            throw new IllegalStateException("Database insert failed", e);
        }
    }

    public int insertReturnKeysTransaction(Connection conn, String sql, Object[] param) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(sql, java.sql.Statement.RETURN_GENERATED_KEYS)) {
            if (param != null) {
                for (int i = 0; i < param.length; i++) {
                    ps.setObject(i + 1, param[i]);
                }
            }
            ps.executeUpdate();
            try (ResultSet rs = ps.getGeneratedKeys()) {
                if (!rs.next()) {
                    throw new SQLException("Insert returned no id");
                }
                return rs.getInt(1);
            }
        }
    }

    public void insertBatch(String sql, Object[][] param) {
        QueryRunner runner = new QueryRunner(MysqlTool.getDataSource());
        try {
            runner.batch(sql, param);
        } catch (SQLException e) {
            throw new IllegalStateException("Database batch failed", e);
        }
    }

    public void insertBatchTransaction(Connection conn, String sql, Object[][] param) throws SQLException {
        QueryRunner runner = new QueryRunner();
        runner.batch(conn, sql, param);
    }

    public void delete(String sql, Object[] param) {
        update(sql, param);
    }

    public void deleteTransaction(Connection conn, String sql, Object[] param) throws SQLException {
        updateTransaction(conn, sql, param);
    }

    public void deleteTransaction(Connection conn, String sql, List<Object> param) throws SQLException {
        Object[] params = new Object[param.size()];
        for (int i = 0; i < param.size(); i++) {
            params[i] = param.get(i);
        }
        updateTransaction(conn, sql, params);
    }

    public void deleteBatchTransaction(Connection conn, String sql, Object[][] param) {
        QueryRunner runner = new QueryRunner();
        try {
            runner.batch(conn, sql, param);
        } catch (SQLException e) {
            throw new IllegalStateException("Transaction batch failed", e);
        }
    }

    public List<String> getColumn(String sql, Object[] param) {
        List<String> list = new LinkedList<>();
        try (Connection conn = MysqlTool.getDataSource().getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            if (param != null) {
                for (int i = 0; i < param.length; i++) {
                    ps.setObject(i + 1, param[i]);
                }
            }
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    list.add(rs.getString(1));
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Database column query failed", e);
        }
        return list;
    }

}
