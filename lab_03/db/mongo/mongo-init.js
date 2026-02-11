// Инициализация MongoDB
// По умолчанию создается 100000 записей
// Для изменения количества записей используй скрипт scripts/refill_database.py

db = db.getSiblingDB("benchmark");

db.users.drop();

var bulk = db.users.initializeUnorderedBulkOp();
var batchSize = 1000;
var total = 100000;

for (var i = 1; i <= total; i++) {
  bulk.insert({
    _id: i,
    name: "User " + i,
    email: "user" + i + "@example.com",
    created_at: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
    last_login_at: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
  });

  if (i % batchSize === 0) {
    bulk.execute();
    bulk = db.users.initializeUnorderedBulkOp();
  }
}

// выполнить "хвост" батча, если он есть
try {
  bulk.execute();
} catch (e) {
  // может быть пустым, тогда ошибка "Invalid Operation" – игнорируем
}

db.users.createIndex({ email: 1 }, { unique: true });
db.users.createIndex({ last_login_at: 1 });



