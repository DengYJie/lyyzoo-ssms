package com.lizhou.filter;

import java.io.IOException;

import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.FilterConfig;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/**
 * 设置request的编码
 * @author bojiangzhou
 *
 */
public class EncodeFilter implements Filter {

	public void destroy() {
		
	}

	public void doFilter(ServletRequest req, ServletResponse rep, FilterChain chain) throws IOException, ServletException {
		HttpServletRequest request = (HttpServletRequest) req;
		HttpServletResponse response = (HttpServletResponse) rep;
		//设置编码格式
		request.setCharacterEncoding("UTF-8");
		//静态资源由容器决定 MIME 类型，强制 text/html 会导致现代浏览器拒绝加载 CSS/JS
		String uri = ((HttpServletRequest) req).getRequestURI();
		if(!uri.matches(".*\\.(css|js|png|gif|jpg|jpeg|ico|woff|woff2|ttf|eot|svg)$")){
			//设置返回类型
			response.setContentType("text/html; charset=utf-8");
		}
		//放行资源
		chain.doFilter(request, response);
	}

	public void init(FilterConfig arg0) throws ServletException {
		
	}

}
