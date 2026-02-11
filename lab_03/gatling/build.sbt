ThisBuild / scalaVersion := "2.13.12"

lazy val GatlingVersion = "3.9.5"

lazy val root = (project in file("."))
  .enablePlugins(GatlingPlugin)
  .settings(
    name := "mongo-postgres-benchmark-gatling",
    libraryDependencies ++= Seq(
      "io.gatling.highcharts" % "gatling-charts-highcharts" % GatlingVersion % Test,
      "io.gatling"            % "gatling-test-framework"    % GatlingVersion % Test,
      "io.gatling"            % "gatling-http"              % GatlingVersion % Test
    ),
    fork := true
  )