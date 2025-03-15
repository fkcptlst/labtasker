#!/bin/bash
set -e

# this script wraps the original docker-entrypoint.sh script of mongodb
# 1. mongodb entrypoint script is called, invoking init.d scripts before starting the server
# 2. the server is started and the entrypoint script waits for the server to be ready
# 3. once the server is ready, the post-init.d scripts are executed

#!/bin/bash

# 设置日志文件
LOG_FILE="/entry.log"

# 确保日志文件存在且可写
touch "$LOG_FILE" 2>/dev/null || {
    echo "无法创建日志文件 $LOG_FILE" >&2
    LOG_FILE="/dev/stdout"
}

# 日志函数 - 同时输出到stderr和日志文件
log_message() {
    echo "$1" | tee -a "$LOG_FILE" >&2
}

# 检查数据库路径
dbPath="/data/db"
if [[ -n "$MONGO_DBPATH" ]]; then
    dbPath="$MONGO_DBPATH"
fi

# 检查是否已初始化
DB_INITIALIZED=false
for path in \
    "$dbPath/WiredTiger" \
    "$dbPath/journal" \
    "$dbPath/local.0" \
    "$dbPath/storage.bson"; do
    if [ -e "$path" ]; then
        DB_INITIALIZED=true
        break
    fi
done

# 检查初始化脚本目录
INIT_SCRIPTS_EXIST=false
if [ -d "/docker-entrypoint-initdb.d/" ] && [ "$(ls -A /docker-entrypoint-initdb.d/ 2>/dev/null)" ]; then
    for f in /docker-entrypoint-initdb.d/*; do
        case "$f" in
            *.sh|*.js)
                INIT_SCRIPTS_EXIST=true
                break
                ;;
        esac
    done
fi

# 检查用户名和密码环境变量
AUTH_CONFIGURED=false
if [ -n "${MONGO_INITDB_ROOT_USERNAME:-}" ] && [ -n "${MONGO_INITDB_ROOT_PASSWORD:-}" ]; then
    AUTH_CONFIGURED=true
fi

# 输出执行条件判断结果
if [ "$DB_INITIALIZED" = true ]; then
    log_message "Will not run /docker-entrypoint-initdb.d/* scripts - Database is already initialized"
    log_message "Database paths found:"
    for path in \
        "$dbPath/WiredTiger" \
        "$dbPath/journal" \
        "$dbPath/local.0" \
        "$dbPath/storage.bson"; do
        if [ -e "$path" ]; then
            log_message "  - $path exists"
        fi
    done
elif [ "$INIT_SCRIPTS_EXIST" = false ] && [ "$AUTH_CONFIGURED" = false ]; then
    log_message "Will not run /docker-entrypoint-initdb.d/* scripts - No initialization scripts found and no authentication configured"
else
    log_message "Will run /docker-entrypoint-initdb.d/* scripts - Database is not initialized"

    if [ "$INIT_SCRIPTS_EXIST" = true ]; then
        log_message "Found initialization scripts:"
        for f in /docker-entrypoint-initdb.d/*; do
            case "$f" in
                *.sh|*.js)
                    log_message "  - $f"
                    ;;
            esac
        done
    fi

    if [ "$AUTH_CONFIGURED" = true ]; then
        log_message "Authentication configured with MONGO_INITDB_ROOT_USERNAME and MONGO_INITDB_ROOT_PASSWORD"
    fi
fi

# 输出环境信息
log_message "MongoDB environment:"
log_message "  - MONGO_DBPATH=${MONGO_DBPATH:-/data/db}"
log_message "  - MONGO_INITDB_DATABASE=${MONGO_INITDB_DATABASE:-}"
log_message "  - MONGO_INITDB_ROOT_USERNAME is ${MONGO_INITDB_ROOT_USERNAME:+set}${MONGO_INITDB_ROOT_USERNAME:-not set}"
log_message "  - MONGO_INITDB_ROOT_PASSWORD is ${MONGO_INITDB_ROOT_PASSWORD:+set}${MONGO_INITDB_ROOT_PASSWORD:-not set}"

# Call the original MongoDB entrypoint script
/usr/local/bin/docker-entrypoint.sh "$@" &

# # Wait for MongoDB to be fully initialized
# echo "Waiting for MongoDB to start..."
# until mongosh --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; do
#   sleep 2
# done
# echo "MongoDB is ready."

# Execute post-init scripts
if [ -d "/docker-entrypoint-post-initdb.d/" ]; then
  echo "Running post-init.d scripts..."
  for script in /docker-entrypoint-post-initdb.d/*; do
    case "$script" in
      *.sh)
        echo "Executing $script"
        . "$script"
        ;;
      *.js)
        echo "Executing $script with mongosh"
        mongosh "$script"
        ;;
      *)
        echo "Ignoring $script (not .sh or .js)"
        ;;
    esac
  done
fi

# Wait for the MongoDB process to end
wait
