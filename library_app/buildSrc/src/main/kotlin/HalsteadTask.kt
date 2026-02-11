package buildsrc

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction
import java.io.File
import kotlin.math.ln

/**
 * Simple Halstead metrics calculator for Kotlin sources.
 * Counts operators/operands with a lightweight tokenizer and fails the build if
 * thresholds are exceeded.
 */
abstract class HalsteadTask : DefaultTask() {

    @get:InputFiles
    abstract val sourceDirs: ListProperty<File>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    /** Max allowed Halstead Volume per file before the task fails. */
    @get:Input
    var maxVolume: Int = 1200

    /** Max allowed Halstead Difficulty per file before the task fails. */
    @get:Input
    var maxDifficulty: Int = 50

    private val operatorKeywords = setOf(
        "if", "else", "for", "while", "when", "try", "catch", "finally", "throw",
        "return", "continue", "break", "class", "object", "interface", "fun",
        "val", "var", "is", "in", "!in", "!is", "as", "as?", "this", "super"
    )

    private val operatorSymbols = setOf(
        "+", "-", "*", "/", "%", "++", "--", "=", "+=", "-=", "*=", "/=", "%=",
        "==", "!=", ">", "<", ">=", "<=", "&&", "||", "!", "?:", "?.", "!!", "::",
        "->", ".", ",", ";", "?", ":", "[", "]", "(", ")", "{", "}"
    )

    @TaskAction
    fun run() {
        val reportLines = mutableListOf<String>()
        val violations = mutableListOf<String>()

        val ktFiles = sourceDirs.get()
            .flatMap { dir ->
                dir.walkTopDown().filter { it.isFile && it.extension == "kt" && !it.inBuildDir() }
            }

        ktFiles.forEach { file ->
            val metrics = computeMetrics(file)
            val volume = metrics.volume()
            val difficulty = metrics.difficulty()

            reportLines += "${file.relativeTo(project.rootDir)}: " +
                    "operators=${metrics.totalOperators}, operands=${metrics.totalOperands}, " +
                    "n1=${metrics.distinctOperators.size}, n2=${metrics.distinctOperands.size}, " +
                    "volume=${"%.2f".format(volume)}, difficulty=${"%.2f".format(difficulty)}"

            if (volume > maxVolume) {
                violations += "${file.relativeTo(project.rootDir)} volume %.2f > %d".format(
                    volume,
                    maxVolume
                )
            }
            if (difficulty > maxDifficulty) {
                violations += "${file.relativeTo(project.rootDir)} difficulty %.2f > %d".format(
                    difficulty,
                    maxDifficulty
                )
            }
        }

        val outFile = outputFile.asFile.get()
        outFile.parentFile.mkdirs()
        outFile.writeText(reportLines.joinToString("\n"))

        if (violations.isNotEmpty()) {
            val preview = violations.joinToString("\n")
            throw org.gradle.api.GradleException(
                "Halstead thresholds exceeded:\n$preview\nSee ${outFile.relativeTo(project.rootDir)} for details."
            )
        }
    }

    private fun computeMetrics(file: File): Metrics {
        val text = file.readText()
        val tokens = tokenize(text)

        val operators = mutableListOf<String>()
        val operands = mutableListOf<String>()

        tokens.forEach { token ->
            when {
                token in operatorKeywords -> operators += token
                token in operatorSymbols -> operators += token
                token.isIdentifierOrLiteral() -> operands += token
            }
        }

        return Metrics(
            distinctOperators = operators.toSet(),
            distinctOperands = operands.toSet(),
            totalOperators = operators.size,
            totalOperands = operands.size
        )
    }

    private fun tokenize(text: String): List<String> {
        val splitRegex = Regex("([\\s()+\\-*/%<>!=&|^?:.,;{}\\[\\]\"]|\".*?\"|'.*?')")
        return text.split(splitRegex)
            .map { it.trim() }
            .filter { it.isNotEmpty() }
    }

    private fun String.isIdentifierOrLiteral(): Boolean {
        return matches(Regex("[A-Za-z_][A-Za-z0-9_]*")) || matches(Regex("-?\\d+(\\.\\d+)?"))
    }

    private fun File.inBuildDir(): Boolean =
        path.contains("${File.separator}build${File.separator}")

    private data class Metrics(
        val distinctOperators: Set<String>,
        val distinctOperands: Set<String>,
        val totalOperators: Int,
        val totalOperands: Int
    ) {
        private fun vocabulary(): Int = (distinctOperators + distinctOperands).size
        private fun length(): Int = totalOperators + totalOperands

        fun volume(): Double {
            val v = vocabulary()
            return if (v == 0 || length() == 0) 0.0 else length() * log2(v.toDouble())
        }

        fun difficulty(): Double {
            if (distinctOperands.isEmpty()) return 0.0
            return (distinctOperators.size / 2.0) * (totalOperands / distinctOperands.size.toDouble())
        }

        private fun log2(x: Double): Double = ln(x) / ln(2.0)
    }
}

