package dbbenchmark

import scala.concurrent.duration._
import scala.util.Random

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class DbBenchmarkSimulation extends Simulation {

  //
  // Базовая конфигурация HTTP
  //
  val baseUrl: String = sys.env.getOrElse("BENCHMARK_BASE_URL", "http://localhost:8000")

  val httpProtocol = http
    .baseUrl(baseUrl)
    .acceptHeader("application/json")

  //
  // Feeder: случайные id пользователей из диапазона 1..100000
  //
  val userIdFeeder = Iterator.continually {
    Map("userId" -> (1 + Random.nextInt(100000)))
  }

  //
  // Сценарий: один запрос GET /users/{id}
  //
  val scn = scenario("GetUserById")
    .feed(userIdFeeder)
    .exec(
      http("get_user_by_id")
        .get("/users/${userId}")
        .check(status.is(200))
    )

  //
  // ПАРАМЕТРЫ ДЛЯ ЭКСПЕРИМЕНТОВ
  //

  // Набор RPS для поиска точки деградации (сценарий 1)
  val rpsLevels: Seq[Double] = Seq(50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600)
  val levelDuration: FiniteDuration = 30.seconds // длительность каждого уровня

  // Максимальный RPS, найденный руками по результатам сценария 1:
  val RPS_MAX: Double = 500

  // Предмаксимальный RPS
  val PREV_RPS_MAX: Double = 450

  // Длительность работы на предмаксимальной нагрузке (сценарий 2)
  val steadyStateDuration: FiniteDuration = 2.minutes

  // Параметры перегрузки/восстановления (сценарий 3)
  val overloadRampDuration: FiniteDuration = 30.seconds  // разгон до перегрузки
  val overloadHoldDuration: FiniteDuration = 1.minute     // удержание перегрузки
  val recoveryRampDuration: FiniteDuration = 30.seconds    // снижение нагрузки
  val recoveryHoldDuration: FiniteDuration = 2.minutes    // восстановление


  //
  // СЦЕНАРИЙ 1: Поиск точки деградации
  // Последовательно запускает несколько фаз с разным RPS.
  //
  val scenario1Injection = rpsLevels.flatMap { rps =>
    Seq(
      rampUsersPerSec(math.max(1.0, rps / 2)).to(rps).during(10.seconds),
      constantUsersPerSec(rps).during(levelDuration)
    )
  }

  //
  // СЦЕНАРИЙ 2: Работа на предмаксимальной нагрузке (PREV_RPS_MAX)
  //
  val scenario2Injection = Seq(
    rampUsersPerSec(math.max(1.0, PREV_RPS_MAX / 2)).to(PREV_RPS_MAX).during(30.seconds),
    constantUsersPerSec(PREV_RPS_MAX).during(steadyStateDuration)
  )

  //
  // СЦЕНАРИЙ 3: Перегрузка и восстановление
  //
  val overloadRps: Double = RPS_MAX

  val scenario3Injection = Seq(
    // Разгон до перегрузки
    rampUsersPerSec(math.max(1.0, RPS_MAX)).to(overloadRps).during(overloadRampDuration),
    constantUsersPerSec(overloadRps).during(overloadHoldDuration),
    // Снижение нагрузки до RPS_MAX / 2 и восстановление
    rampUsersPerSec(overloadRps).to(RPS_MAX / 2).during(recoveryRampDuration),
    constantUsersPerSec(RPS_MAX / 2).during(recoveryHoldDuration)
  )

  //
  // Выбор сценария через системное свойство GATLING_SCENARIO:
  // -Dgatling.options="-Dscenario=1" и т.п.
  //
  val scenarioId: String = System.getProperty("scenario", "1")

  scenarioId match {
    case "1" =>
      setUp(
        scn.inject(scenario1Injection).protocols(httpProtocol)
      )

    case "2" =>
      setUp(
        scn.inject(scenario2Injection).protocols(httpProtocol)
      )

    case "3" =>
      setUp(
        scn.inject(scenario3Injection).protocols(httpProtocol)
      )

    case other =>
      println(s"Unknown scenario id: $other, defaulting to scenario 1")
      setUp(
        scn.inject(scenario1Injection).protocols(httpProtocol)
      )
  }
}



