# Сүйрлийн нөхөн сэргээлт (Disaster Recovery)

## Нөөц хуулбараас сэргээх (Restore from backup)

POS систем өдөр бүр автоматаар нөөц хуулбар үүсгэдэг (`backups/pos_YYYY-MM-DD.db`).

### Алхамууд (Steps)

1. **Серверийг зогсоох:**
   ```bash
   sudo systemctl stop pos
   # or
   docker-compose down
   ```

2. **Одоогийн өгөгдлийн сангийн нөөц хуулбар үүсгэх (хэрэв боломжтой бол):**
   ```bash
   cp pos.db pos.db.broken.$(date +%Y%m%d_%H%M%S)
   ```

3. **Сүүлийн ажиллагаатай нөөц хуулбарыг шалгах:**
   ```bash
   ls -lt backups/pos_*.db | head -5
   ```

4. **Нөөц хуулбарын бүрэн бүтэн байдлыг шалгах:**
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('backups/pos_YYYY-MM-DD.db')
   result = conn.execute('PRAGMA integrity_check').fetchone()[0]
   assert result == 'ok', f'Backup corrupted: {result}'
   print('OK')
   "
   ```

5. **Нөөц хуулбарыг идэвхтэй болгох:**
   ```bash
   cp backups/pos_YYYY-MM-DD.db pos.db
   chmod 644 pos.db
   ```

6. **Серверийг эхлүүлэх:**
   ```bash
   sudo systemctl start pos
   # or
   docker-compose up -d
   ```

7. **Систем ачаалсныг шалгах:**
   ```bash
   curl http://localhost:8765/api/health
   # {"status":"ok"}
   ```

## Гар аргаар нөөц хуулбар үүсгэх (Manual backup)

```bash
# Web интерфейсээр:
# Тохиргоо → Нөөц хуулбар → "Нөөц хуулбар үүсгэх" товч

# Эсвэл командын мөрөөр:
curl -X POST http://localhost:8765/settings/backup \
  -H "X-CSRF-Token: YOUR_CSRF_TOKEN"
```

## Нөөц хуулбарын хадгалалт (Backup retention)

- Өдөр бүр 1 нөөц хуулбар (анхны борлуулалт хийхэд)
- Анхдагч хадгалах хугацаа: 30 хоног (`backup_retention_days` тохиргоо)
- Schema update бүрийн өмнө хамгаалалтын нөөц хуулбар үүсгэдэг

## Өгөгдлийн сан гэмтэлтэй бол (Database corruption)

Хэрэв `PRAGMA integrity_check` алдаа гаргавал:

1. WAL файлуудыг шалгах:
   ```bash
   ls -la pos.db pos.db-wal pos.db-shm
   ```
2. WAL checkpoint хийх:
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('pos.db')
   conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
   conn.close()
   "
   ```
3. Хэрэв засагдахгүй бол дээрх сэргээх алхмуудыг дагах

## Нөөц хуулбар автоматжуулалт (Off-site backup — Linux)

```bash
# crontab -e
0 2 * * * rsync -avz /opt/pos/backups/ user@backup-server:/backups/pos/
```
