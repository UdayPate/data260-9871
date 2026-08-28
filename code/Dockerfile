# Use Nginx as the base image
FROM nginx:alpine

# Remove default Nginx HTML files
RUN rm -rf /usr/share/nginx/html/*

# Copy frontend files (HTML, JS) into the Nginx web root
COPY web_application/ /usr/share/nginx/html/

# Configure Nginx to listen on PORT_BASE (8871) instead of default 80
RUN sed -i 's/listen\s*80;/listen 8871;/' /etc/nginx/conf.d/default.conf

# Expose PORT_BASE
EXPOSE 8871

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]